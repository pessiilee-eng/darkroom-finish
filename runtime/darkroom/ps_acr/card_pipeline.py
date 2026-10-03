#!/usr/bin/env python3
"""The ONLY legitimate finishing entry point (skill S7).

Renders candidates strictly from schema-valid technique cards:

  theme manifest (knowledge/themes/<theme>.manifest.json)
    -> ordered card set (knowledge/cards/*.json, schema-validated here)
    -> merged ACR parameters (absolute value_specs only, ranges enforced)
    -> XMP sidecar -> Photoshop/ACR headless render
    -> master TIFF (double render, pixel-strip replay check) + viewing JPEG
    -> per-candidate manifest embedding card ids/versions/hashes + gates

Refuses to run if: any card fails schema validation; any card is not
`frozen` (or `candidate` when --allow-candidate, recorded in the manifest as
user_confirmation_pending); any parameter falls outside its allowed_range; or
a source hash mismatches the frozen inventory.
"""

import argparse
import hashlib
import json
import platform
import os
import plistlib
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))
from darkroom.acr_geometry import merge_geometry, validate_crop_parameters, geometry_evidence, read_raw_orientation  # noqa: E402
sys.path.insert(0, str(PROJECT / "darkroom" / "cards"))
sys.path.insert(0, str(Path(__file__).parent))
from validate import load_validator, validate_card  # noqa: E402
from operation_registry import (  # noqa: E402
    OperationRegistryError,
    field_to_xmp_mapping,
    field_to_xmp_transport_mapping,
    load_operation_registry,
    native_parameter_value,
    operation_registry_ref,
    operations_by_field,
    validate_mask_graph,
)
from minimal_loop import tiff_strip_sha256  # noqa: E402

PS_BUNDLE_ID = "com.adobe.Photoshop"
PS_INFO_PLIST = Path(os.environ.get("DARKROOM_PHOTOSHOP_APP", "unconfigured.app")) / "Contents/Info.plist"
ACR_INFO_PLISTS = (
    Path("/Library/Application Support/Adobe/Plug-Ins/CC/File Formats/Camera Raw.plugin/Contents/Info.plist"),
    Path("/Library/Application Support/Adobe/Plug-Ins/CC/File Formats/Camera Raw.plugin/Contents/Resources/Info.plist"),
)

OPERATION_REGISTRY = load_operation_registry()
OPERATION_REGISTRY_REF = operation_registry_ref(OPERATION_REGISTRY)
# formula-dsl Identifier (lowercase) -> crs XMP key, generated from registry evidence
FIELD_TO_CRS = field_to_xmp_mapping(OPERATION_REGISTRY)
FIELD_TO_TRANSPORT = field_to_xmp_transport_mapping(OPERATION_REGISTRY)
OPERATIONS_BY_FIELD = operations_by_field(OPERATION_REGISTRY)
TRANSPORTS_BY_KEY = {
    transport["key"]: transport for transport in FIELD_TO_TRANSPORT.values()
}

XMP_TEMPLATE = """<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="darkroom-finish card_pipeline">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
    crs:ProcessVersion="15.4"
    crs:HasSettings="True"{attrs}>
{children}
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
"""


def _xml_attribute(value: object) -> str:
    return xml_escape(str(value), {'"': "&quot;"})


def _decimal_text(value: Decimal | str) -> str:
    parsed = value if isinstance(value, Decimal) else Decimal(value)
    text = format(parsed, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


LOCAL_XMP_DEFAULTS = {
    "LocalExposure": "0",
    "LocalHue": "0",
    "LocalSaturation": "0",
    "LocalContrast": "0",
    "LocalClarity": "0",
    "LocalSharpness": "0",
    "LocalBrightness": "0",
    "LocalToningHue": "0",
    "LocalToningSaturation": "0",
    "LocalExposure2012": "0",
    "LocalContrast2012": "0",
    "LocalHighlights2012": "0",
    "LocalShadows2012": "0",
    "LocalWhites2012": "0",
    "LocalBlacks2012": "0",
    "LocalClarity2012": "0",
    "LocalDehaze": "0",
    "LocalLuminanceNoise": "0",
    "LocalMoire": "0",
    "LocalDefringe": "0",
    "LocalTemperature": "0",
    "LocalTint": "0",
    "LocalTexture": "0",
}
LOCAL_FIELD_TO_XMP = {
    "exposure2012": "LocalExposure2012",
    "contrast2012": "LocalContrast2012",
    "highlights2012": "LocalHighlights2012",
    "shadows2012": "LocalShadows2012",
    "whites2012": "LocalWhites2012",
    "blacks2012": "LocalBlacks2012",
    "clarity2012": "LocalClarity2012",
    "dehaze": "LocalDehaze",
    "temperature": "LocalTemperature",
    "tint": "LocalTint",
    "texture": "LocalTexture",
    "saturation": "LocalSaturation",
    "sharpness": "LocalSharpness",
}
LOCAL_NORMALIZED_FIELDS = frozenset({
    "contrast2012", "highlights2012", "shadows2012", "whites2012", "blacks2012",
    "clarity2012", "dehaze", "temperature", "tint", "texture", "saturation", "sharpness",
})


def _mask_attributes(attributes: dict[str, object], indent: str) -> str:
    return ("\n" + indent).join(
        f'crs:{key}="{_xml_attribute(value)}"' for key, value in attributes.items()
    )


def _render_brush(mask: dict, indent: str = "         ", raw_orientation: int | None = None) -> str:
    paints: list[str] = []
    for dab in mask["dabs"]:
        center_weight = Decimal("1") - Decimal(dab["feather"])
        attrs = {
            "What": "Mask/Paint",
            "MaskActive": "true",
            "MaskBlendMode": "0",
            "MaskInverted": "false",
            "MaskValue": "1",
            "Radius": _decimal_text(dab["radius"]),
            "Flow": _decimal_text(dab["flow"]),
            "CenterWeight": _decimal_text(center_weight),
        }
        x, y = Decimal(dab['x']), Decimal(dab['y'])
        if raw_orientation == 6:
            x, y = y, Decimal(1) - x
        elif raw_orientation == 8:
            x, y = Decimal(1) - y, x
        dab_value = f"d {_decimal_text(x)} {_decimal_text(y)}"
        paints.append(
            f"{indent}  <rdf:li>\n"
            f"{indent}   <rdf:Description\n{indent}    {_mask_attributes(attrs, indent + '    ')}>\n"
            f"{indent}    <crs:Dabs>\n{indent}     <rdf:Seq>\n"
            f"{indent}      <rdf:li>{dab_value}</rdf:li>\n"
            f"{indent}     </rdf:Seq>\n{indent}    </crs:Dabs>\n"
            f"{indent}   </rdf:Description>\n{indent}  </rdf:li>"
        )
    aggregate = {
        "What": "Mask/Aggregate",
        "MaskActive": "true",
        "MaskName": mask["id"],
        "MaskBlendMode": "0",
        "MaskInverted": "false",
        "MaskValue": "1",
    }
    return (
        f"{indent}<rdf:li>\n{indent} <rdf:Description\n"
        f"{indent}  {_mask_attributes(aggregate, indent + '  ')}>\n"
        f"{indent}  <crs:Masks>\n{indent}   <rdf:Seq>\n"
        + "\n".join(paints)
        + f"\n{indent}   </rdf:Seq>\n{indent}  </crs:Masks>\n"
        f"{indent} </rdf:Description>\n{indent}</rdf:li>"
    )


def _render_linear(mask: dict, indent: str = "         ") -> str:
    attrs = {
        "What": "Mask/Gradient",
        "MaskActive": "true",
        "MaskName": mask["id"],
        "MaskBlendMode": "0",
        "MaskInverted": "false",
        "MaskValue": "1",
        "ZeroX": _decimal_text(mask["start"]["x"]),
        "ZeroY": _decimal_text(mask["start"]["y"]),
        "FullX": _decimal_text(mask["end"]["x"]),
        "FullY": _decimal_text(mask["end"]["y"]),
    }
    return f"{indent}<rdf:li\n{indent} {_mask_attributes(attrs, indent + ' ')}/>"


def _render_radial(mask: dict, indent: str = "         ") -> str:
    cx, cy = Decimal(mask["center"]["x"]), Decimal(mask["center"]["y"])
    rx, ry = Decimal(mask["radius_x"]), Decimal(mask["radius_y"])
    attrs = {
        "What": "Mask/CircularGradient",
        "MaskActive": "true",
        "MaskName": mask["id"],
        "MaskBlendMode": "0",
        "MaskInverted": str(mask["inverted"]).lower(),
        "MaskValue": "1",
        "Top": _decimal_text(cy - ry),
        "Left": _decimal_text(cx - rx),
        "Bottom": _decimal_text(cy + ry),
        "Right": _decimal_text(cx + rx),
        "Angle": _decimal_text(mask["angle_degrees"]),
        "Midpoint": "50",
        "Roundness": "0",
        "Feather": _decimal_text(Decimal(mask["feather"]) * Decimal("100")),
        "Flipped": "false",
        "Version": "2",
    }
    return f"{indent}<rdf:li\n{indent} {_mask_attributes(attrs, indent + ' ')}/>"


def _render_luminance(mask: dict, indent: str = "         ") -> str:
    minimum = Decimal(mask["minimum"])
    maximum = Decimal(mask["maximum"])
    feather = Decimal(mask["feather"])
    lum_range = " ".join(
        _decimal_text(value)
        for value in (
            max(Decimal("0"), minimum - feather),
            minimum,
            maximum,
            min(Decimal("1"), maximum + feather),
        )
    )
    mask_attrs = {
        "What": "Mask/RangeMask",
        "MaskActive": "true",
        "MaskName": mask["id"],
        "MaskBlendMode": "0",
        "MaskInverted": "false",
        "MaskValue": "1",
    }
    range_attrs = {
        "Version": "3",
        "Type": "2",
        "Invert": "false",
        "SampleType": "1",
        "LumRange": lum_range,
    }
    return (
        f"{indent}<rdf:li>\n{indent} <rdf:Description\n"
        f"{indent}  {_mask_attributes(mask_attrs, indent + '  ')}>\n"
        f"{indent}  <crs:CorrectionRangeMask\n"
        f"{indent}   {_mask_attributes(range_attrs, indent + '   ')}/>\n"
        f"{indent} </rdf:Description>\n{indent}</rdf:li>"
    )


def render_mask_graph(graph: dict, raw_orientation: int | None = None) -> str:
    """Render a validated mask_graph/v1 as deterministic ACR 16.5 RDF XML."""

    validate_mask_graph(graph)
    if raw_orientation not in (None, 1, 6, 8):
        raise ValueError('unsupported RAW orientation for mask transport')
    if raw_orientation in (6, 8) and any(mask['type'] != 'brush' for group in graph['groups'] for mask in group['masks']):
        raise ValueError('native oriented geometry currently supports brush masks only')
    groups: list[str] = []
    for group in graph["groups"]:
        native_adjustments = dict(LOCAL_XMP_DEFAULTS)
        for field, value in group["local_adjustments"].items():
            native_value = Decimal(value)
            if field in LOCAL_NORMALIZED_FIELDS:
                native_value /= Decimal("100")
            native_adjustments[LOCAL_FIELD_TO_XMP[field]] = _decimal_text(native_value)
        sync_id = hashlib.sha256(
            f"{graph['graph_sha256']}:{group['id']}".encode("utf-8")
        ).hexdigest()[:32].upper()
        correction_attrs = {
            "What": "Correction",
            "CorrectionAmount": "1",
            "CorrectionActive": "true",
            "CorrectionName": group["name"],
            "CorrectionSyncID": sync_id,
            **native_adjustments,
        }
        spatial_xml: list[str] = []
        for mask in group["masks"]:
            if mask["type"] == "brush":
                spatial_xml.append(_render_brush(mask, raw_orientation=raw_orientation))
            elif mask["type"] == "linear_gradient":
                spatial_xml.append(_render_linear(mask))
            elif mask["type"] == "radial_gradient":
                spatial_xml.append(_render_radial(mask))
            elif mask["type"] == "luminance_range":
                spatial_xml.append(_render_luminance(mask))
        correction_masks = ""
        if spatial_xml:
            correction_masks = (
                "\n      <crs:CorrectionMasks>\n       <rdf:Seq>\n"
                + "\n".join(spatial_xml)
                + "\n       </rdf:Seq>\n      </crs:CorrectionMasks>"
            )
        range_attrs = {
            "Version": "1", "Type": "0", "ColorAmount": "0.5",
            "LumMin": "0", "LumMax": "1", "LumFeather": "0.5",
            "DepthMin": "0", "DepthMax": "1", "DepthFeather": "0.5",
        }
        groups.append(
            "     <rdf:li>\n      <rdf:Description\n       "
            + _mask_attributes(correction_attrs, "       ")
            + ">"
            + correction_masks
            + "\n      <crs:CorrectionRangeMask\n       "
            + _mask_attributes(range_attrs, "       ")
            + "/>\n      </rdf:Description>\n     </rdf:li>"
        )
    return (
        "    <crs:MaskGroupBasedCorrections>\n     <rdf:Seq>\n"
        + "\n".join(groups)
        + "\n     </rdf:Seq>\n    </crs:MaskGroupBasedCorrections>"
    )


def render_xmp_sidecar(
    params: dict[str, str | list[str]], mask_graph: dict | None = None, *, raw_orientation: int | None = None
) -> str:
    """Render registry-backed XMP attributes and ordered RDF sequences."""
    validate_crop_parameters(params)
    attributes: dict[str, str] = {}
    sequences: dict[str, list[str]] = {}
    for key, value in params.items():
        transport = TRANSPORTS_BY_KEY.get(key)
        if isinstance(value, list):
            if transport is None or transport["kind"] != "xmp_rdf_seq":
                raise OperationRegistryError(f"unregistered XMP RDF sequence: {key}")
            sequences[key] = value
            for companion_key, companion_value in transport.get(
                "companion_attributes", {}
            ).items():
                existing = attributes.get(companion_key)
                if existing is not None and existing != companion_value:
                    raise OperationRegistryError(
                        f"conflicting XMP companion attribute: {companion_key}"
                    )
                attributes[companion_key] = companion_value
        else:
            if transport is None:
                raise OperationRegistryError(f"unregistered XMP attribute: {key}")
            if transport["kind"] != "xmp_attribute":
                raise OperationRegistryError(f"XMP transport/value mismatch: {key}")
            attributes[key] = value

    attr_text = "".join(
        f'\n    crs:{key}="{_xml_attribute(value)}"'
        for key, value in sorted(attributes.items())
    )
    children: list[str] = []
    for key, values in sorted(sequences.items()):
        items = "\n".join(f"      <rdf:li>{xml_escape(value)}</rdf:li>" for value in values)
        children.append(
            f"    <crs:{key}>\n     <rdf:Seq>\n{items}\n     </rdf:Seq>\n"
            f"    </crs:{key}>"
        )
    if mask_graph is not None:
        children.append(render_mask_graph(mask_graph, raw_orientation))
    return XMP_TEMPLATE.format(attrs=attr_text, children="\n".join(children))

JSX_TIFF = """
(function() {{
  var doc = app.open(new File({src}));
  doc.bitsPerChannel = BitsPerChannelType.SIXTEEN;
  doc.convertProfile("sRGB IEC61966-2.1", Intent.RELATIVECOLORIMETRIC, true, true);
  var o = new TiffSaveOptions(); o.imageCompression = TIFFEncoding.NONE;
  o.embedColorProfile = true; o.layers = false;
  doc.saveAs(new File({out}), o, true, Extension.LOWERCASE);
  doc.close(SaveOptions.DONOTSAVECHANGES);
}})();
"""

JSX_JPEG = """
(function() {{
  var doc = app.open(new File({src}));
  doc.bitsPerChannel = BitsPerChannelType.EIGHT;
  doc.convertProfile("sRGB IEC61966-2.1", Intent.RELATIVECOLORIMETRIC, true, true);
  var o = new JPEGSaveOptions(); o.quality = 11; o.embedColorProfile = true;
  doc.saveAs(new File({out}), o, true, Extension.LOWERCASE);
  doc.close(SaveOptions.DONOTSAVECHANGES);
}})();
"""


def render_document_jsx(source: Path, output: Path, template: str, xmp_text: str) -> str:
    """JPEG needs explicit ACR settings; app.open can ignore its XMP sidecar.

    The XMPp open descriptor consumes the same registry-compiled XMP as RAW.
    Only JPEG changes transport; neither its source nor its staged bytes change.
    This lower-level transport is retained; JPEG input is not the public CLI.
    """
    rendered = template.format(src=json.dumps(str(source)), out=json.dumps(str(output)))
    if source.suffix.lower() not in {".jpg", ".jpeg"}:
        return rendered
    opening = f'''var settings = new ActionDescriptor();
  settings.putString(charIDToTypeID("XMPp"), {json.dumps(xmp_text)});
  var request = new ActionDescriptor();
  request.putPath(charIDToTypeID("null"), new File({json.dumps(str(source))}));
  request.putObject(charIDToTypeID("As  "), stringIDToTypeID("Adobe Camera Raw"), settings);
  request.putBoolean(stringIDToTypeID("overrideOpen"), true);
  executeAction(charIDToTypeID("Opn "), request, DialogModes.NO);
  var doc = app.activeDocument;'''
    if template == JSX_TIFF:
        opening += '\n  doc.bitsPerChannel = BitsPerChannelType.SIXTEEN;'
    return rendered.replace(f'var doc = app.open(new File({json.dumps(str(source))}));', opening, 1)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def installed_version(plist_paths: tuple[Path, ...]) -> str:
    """Report installed metadata; absent/unreadable metadata is not a version."""
    for path in plist_paths:
        try:
            with path.open("rb") as handle:
                info = plistlib.load(handle)
            version = info.get("CFBundleShortVersionString")
            build = info.get("CFBundleVersion")
            if isinstance(version, str) and version.strip():
                return f"{version} ({build})" if build and build != version else version
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return "unknown"


def render_environment() -> dict:
    system = platform.system() or "unknown"
    version = platform.mac_ver()[0] if system == "Darwin" else platform.release()
    return {
        "photoshop": installed_version((PS_INFO_PLIST,)),
        "camera_raw": installed_version(ACR_INFO_PLISTS),
        "os": f"{'macOS' if system == 'Darwin' else system} {version or 'unknown'} {platform.machine() or 'unknown'}",
    }


def stage_raw(source: Path, staged: Path, frozen_hash: str) -> None:
    if not staged.exists():
        shutil.copy2(source, staged)
    if sha256(staged) != frozen_hash:
        raise SystemExit(f"REFUSED: staged source hash mismatch: {staged}")


def verify_frozen_hash(path: Path, frozen_hash: str) -> tuple[bool, str | None, str | None]:
    try:
        actual_hash = sha256(path)
    except OSError as exc:
        return False, None, f"{path}: {type(exc).__name__}: {exc}"
    if actual_hash != frozen_hash:
        return False, actual_hash, f"hash mismatch: {path}"
    return True, actual_hash, None


def render_passed(gates: dict, preview_only: bool) -> bool:
    required = ["G0_source_integrity", "G1_params_frozen"]
    if not preview_only:
        required.append("G2_replay_deterministic")
    return all(gates.get(gate) is True for gate in required)


def run_jsx_file(jsx_path: Path, timeout_s: int = 900) -> str:
    app_path = os.environ.get('DARKROOM_PHOTOSHOP_APP')
    if not app_path or not (Path(app_path) / 'Contents/Info.plist').is_file():
        raise ValueError('Select the installed Photoshop application using scripts/darkroom.py')
    script = (
        f'with timeout of {timeout_s} seconds\n'
        f'set js to read POSIX file {json.dumps(str(jsx_path), ensure_ascii=False)} as «class utf8»\n'
        f'tell application {json.dumps(app_path, ensure_ascii=False)} to do javascript js\n'
        f'end timeout'
    )
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True,
                          timeout=timeout_s + 60)
    if proc.returncode != 0:
        raise RuntimeError(f"osascript failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def load_cards(theme_manifest: dict, allow_candidate: bool) -> list[dict]:
    validator, schemas = load_validator()
    cards = []
    for card_file in theme_manifest["cards"]:
        path = PROJECT / "knowledge" / "cards" / card_file
        if not path.exists():
            raise SystemExit(f"REFUSED: card missing: {card_file}")
        errs = validate_card(path, validator, schemas, OPERATION_REGISTRY)
        if errs:
            raise SystemExit(f"REFUSED: card {card_file} fails schema: {errs}")
        card = json.loads(path.read_text())
        if card["status"] == "frozen":
            pass
        elif card["status"] == "candidate" and allow_candidate:
            pass
        else:
            raise SystemExit(
                f"REFUSED: card {card['card_id']} status={card['status']}; "
                f"only frozen (or candidate with --allow-candidate) may render")
        card["_sha256"] = sha256(path)
        card["_file"] = card_file
        cards.append(card)
    return cards


def in_range(value: str, rng: dict | None) -> bool:
    if rng is None:
        return True
    v, lo, hi = float(value), float(rng["lower"]), float(rng["upper"])
    inc = rng["inclusivity"]
    lo_ok = v >= lo if inc in ("closed", "left_closed") else v > lo
    hi_ok = v <= hi if inc in ("closed", "right_closed") else v < hi
    return lo_ok and hi_ok


def resolve_params(cards: list[dict], overrides: dict[str, dict]) -> dict[str, str | list[str]]:
    """Merge card parameter_rules in card order into {crs_attr: value}.

    Only absolute value_specs are supported in this version; formula specs
    refuse (no formula evaluator is wired to measurements yet). `overrides`
    maps field -> {value, card_id}: per-photo intent tweaks that must stay
    inside the owning card's allowed_range. Enum overrides additionally carry
    the owning registry `domain_ref` and use canonical tokens.
    """
    resolved: dict[str, str | list[str]] = {}
    ranges: dict[str, dict | None] = {}
    for card in cards:
        for rule in card["parameter_rules"]:
            field = rule["field"]
            spec = rule["value_spec"]
            if spec["kind"] != "absolute":
                raise SystemExit(
                    f"REFUSED: {card['card_id']}.{field} uses formula value_spec; "
                    f"formula evaluation is not wired yet")
            scalar = spec["value"]
            try:
                value = native_parameter_value(field, scalar, OPERATION_REGISTRY)
            except OperationRegistryError as exc:
                raise SystemExit(f"REFUSED: {card['card_id']}.{field}: {exc}") from exc
            if scalar["type"] in ("decimal", "integer"):
                if not in_range(value, rule["allowed_range"]):
                    raise SystemExit(
                        f"REFUSED: {card['card_id']}.{field}={value} outside allowed_range")
            crs = FIELD_TO_CRS.get(field)
            if crs is None:
                raise SystemExit(f"REFUSED: unmapped field {field}")
            resolved[crs] = value
            ranges[field] = rule["allowed_range"]
    for field, ov in overrides.items():
        if field not in ranges:
            raise SystemExit(f"REFUSED: override for {field} has no owning card rule")
        operation = OPERATIONS_BY_FIELD[field]
        if operation["value_type"] == "enum":
            scalar = {
                "type": "enum",
                "domain_ref": ov.get("domain_ref"),
                "value": ov["value"],
            }
            try:
                override_value = native_parameter_value(field, scalar, OPERATION_REGISTRY)
            except OperationRegistryError as exc:
                raise SystemExit(f"REFUSED: override {field}: {exc}") from exc
        elif operation["value_type"] == "curve":
            scalar = ov.get("value")
            if not isinstance(scalar, dict) or scalar.get("type") != "curve":
                raise SystemExit(f"REFUSED: override {field} requires a typed curve value")
            try:
                override_value = native_parameter_value(field, scalar, OPERATION_REGISTRY)
            except OperationRegistryError as exc:
                raise SystemExit(f"REFUSED: override {field}: {exc}") from exc
        else:
            override_value = ov["value"]
            if not in_range(override_value, ranges[field]):
                raise SystemExit(f"REFUSED: override {field}={override_value} outside card range")
        resolved[FIELD_TO_CRS[field]] = override_value
    if "Temperature" in resolved:
        # crs Temperature only applies with an explicit custom white balance
        resolved.setdefault("WhiteBalance", "Custom")
    return resolved


def resolve_mask_graph(cards: list[dict]) -> dict | None:
    graphs = [card["mask_recipe"] for card in cards if card.get("mask_recipe") is not None]
    if len(graphs) > 1:
        raise SystemExit("REFUSED: multiple mask_graph cards require an explicit merge contract")
    if not graphs:
        return None
    try:
        validate_mask_graph(graphs[0])
    except OperationRegistryError as exc:
        raise SystemExit(f"REFUSED: {exc}") from exc
    return graphs[0]


def resolve_postprocess_recipe(cards: list[dict]) -> dict | None:
    recipes = [card["postprocess_recipe"] for card in cards if card.get("postprocess_recipe")]
    if len(recipes) > 1:
        raise SystemExit("REFUSED: multiple raster recipes require an explicit merge contract")
    return recipes[0] if recipes else None


def postprocess_candidate(master: Path, replay: Path, jpeg: Path, recipe: dict,
                          run_dir: Path, identifier: str, python: str) -> dict:
    """Keep the Adobe bases and apply one admitted, frozen local recipe twice."""
    implementations = {
        "local.harmonic_tone_balance": "local_tone_balance.py",
        "local.skin_control_field": "local_skin_field.py",
        "local.skin_texture_smoothing": "local_skin_texture.py",
        "local.sun_glow": "local_sun_glow.py",
        "local.sampled_frequency_repair": "local_sampled_repair.py",
        "local.same_source_restore": "local_same_source_restore.py",
        "local.tonal_brush": "local_tonal_brush.py",
        "local.spatial_light": "local_spatial_light.py",
        "local.same_image_clone": "local_same_image_clone.py",
    }
    module = implementations.get(recipe.get("operation_id"))
    if module is None:
        raise RuntimeError("unsupported local recipe operation")
    implementation = PROJECT / "darkroom" / "ps_acr" / module
    frozen_code_hash = sha256(implementation)
    dependencies = {
        "operation_registry.py": PROJECT / "scripts" / "operation_registry.py",
    }
    if recipe["operation_id"] in {"local.skin_control_field", "local.skin_texture_smoothing", "local.sun_glow", "local.sampled_frequency_repair", "local.same_source_restore", "local.tonal_brush", "local.spatial_light", "local.same_image_clone"}:
        dependencies["local_tone_balance.py"] = implementation.with_name("local_tone_balance.py")
        dependencies["verify_ai_darkroom_contracts.py"] = PROJECT / "scripts" / "verify_ai_darkroom_contracts.py"
    if recipe["operation_id"] == "local.tonal_brush":
        dependencies["local_skin_field.py"] = implementation.with_name("local_skin_field.py")
        dependencies["local_same_source_restore.py"] = implementation.with_name("local_same_source_restore.py")
    if recipe["operation_id"] == "local.same_image_clone":
        dependencies["local_same_source_restore.py"] = implementation.with_name("local_same_source_restore.py")
    frozen_dependencies = {name: sha256(path) for name, path in dependencies.items()}
    snapshot_dir = run_dir / f"{identifier}-implementation"
    snapshot_dir.mkdir(exist_ok=True)
    for name, source in {module: implementation, **dependencies}.items():
        shutil.copy2(source, snapshot_dir / name)
    recipe_path = run_dir / f"{identifier}-tone-recipe.json"
    recipe_path.write_text(json.dumps(recipe, indent=2) + "\n")
    frozen_recipe_hash = sha256(recipe_path)
    items = []
    pending_outputs = []
    corrected_jpeg = run_dir / f"{identifier}-tone.jpg"
    for label, target in (("master", master), ("replay", replay)):
        base = run_dir / f"{identifier}-{label}-acr-base.tif"
        corrected = run_dir / f"{identifier}-{label}-tone.tif"
        evidence_path = run_dir / f"{identifier}-{label}-tone-evidence.json"
        shutil.copy2(target, base)
        command = [python, str(implementation), "--input", str(base),
                   "--output", str(corrected), "--recipe", str(recipe_path),
                   "--evidence", str(evidence_path)]
        if label == "master":
            command += ["--jpeg", str(corrected_jpeg)]
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=180)
        result = json.loads(evidence_path.read_text())
        if (result["implementation_sha256"] != frozen_code_hash
                or result["recipe_sha256"] != recipe["recipe_sha256"]
                or not result["input_unchanged"]
                or not all(region["outside_support_unchanged" if recipe["operation_id"] in {"local.sun_glow", "local.sampled_frequency_repair", "local.same_source_restore", "local.tonal_brush", "local.spatial_light", "local.same_image_clone"}
                                      else "outside_polygon_unchanged"] for region in result["regions"])):
            raise RuntimeError("local tone preservation checks failed")
        if recipe["operation_id"] in {"local.skin_control_field", "local.skin_texture_smoothing", "local.sun_glow", "local.sampled_frequency_repair", "local.same_source_restore", "local.tonal_brush", "local.spatial_light", "local.same_image_clone"} and result.get("dependency_sha256") != frozen_dependencies:
            raise RuntimeError("local skin field dependency fingerprint mismatch")
        pending_outputs.append((corrected, target))
        items.append({"role": label, "base": str(base.relative_to(PROJECT)),
                      "evidence": str(evidence_path.relative_to(PROJECT)), **result})
    intact = (sha256(implementation) == frozen_code_hash
              and sha256(recipe_path) == frozen_recipe_hash
              and all(sha256(path) == frozen_dependencies[name] for name, path in dependencies.items()))
    if not intact:
        raise RuntimeError("local tone implementation or recipe changed during render")
    if items[0]["output_pixel_sha256"] != items[1]["output_pixel_sha256"]:
        raise RuntimeError("local tone replay pixel mismatch")
    for corrected, target in pending_outputs:
        corrected.replace(target)
    corrected_jpeg.replace(jpeg)
    return {"recipe_file": str(recipe_path.relative_to(PROJECT)),
            "recipe_file_sha256": frozen_recipe_hash,
            "implementation_sha256": frozen_code_hash, "frozen_unchanged": intact,
            "dependency_sha256": frozen_dependencies,
            "implementation_snapshot_directory": str(snapshot_dir.relative_to(PROJECT)),
            "snapshot_scope": "source audit attachment; replay uses project imports and recorded runtime, not a standalone package",
            "passes": items}


def src_nef2(args, stem):
    raw_dir = Path(args.album) / args.raw_subdir if args.raw_subdir else Path(args.album)
    return raw_dir / f"{stem}{args.ext}"


def validate_base_master(base_manifest_path, gid, stem, source_hash, params, mask_graph):
    """Bind an existing verified master to this exact source and color recipe."""
    base_path = Path(base_manifest_path).resolve()
    base = json.loads(base_path.read_text())
    if base.get('frame') != stem or base.get('scene_group') != gid or base.get('source_sha256') != source_hash:
        raise ValueError('base master source/frame binding mismatch')
    if not all(base.get('gates', {}).get(gate) is True for gate in
               ('G0_source_integrity', 'G1_params_frozen', 'G2_replay_deterministic')):
        raise ValueError('base master must have passed G0/G1/G2')
    if base.get('resolved_params') != params or base.get('mask_graph_sha256') != (
            None if mask_graph is None else mask_graph['graph_sha256']):
        raise ValueError('base master global parameters or Adobe masks differ; refusing unrendered changes')
    master = (PROJECT / base['master_tiff']).resolve()
    if not master.is_relative_to(PROJECT.resolve()) or not master.is_file():
        raise ValueError('base master must be an existing project TIFF')
    if sha256(master) != base.get('master_tiff_sha256') or tiff_strip_sha256(master) != base.get('master_pixel_strip_sha256'):
        raise ValueError('base master file or pixel hash mismatch')
    return base_path, base, master


def export_base_master_jpeg(master: Path, jpeg: Path, python: str) -> dict:
    """Export only a viewing JPEG from verified RGB16 pixels, without an effect recipe."""
    adapter = PROJECT / 'darkroom' / 'ps_acr' / 'local_tone_balance.py'
    frozen = {'card_pipeline.py': sha256(Path(__file__)), 'local_tone_balance.py': sha256(adapter)}
    master_hash = sha256(master)
    code = '''import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import numpy as np
from PIL import Image
from local_tone_balance import load_rgb16_strip
data,pixels,icc=load_rgb16_strip(sys.argv[2])
rgb8=((pixels.astype(np.uint32)+128)//257).astype(np.uint8)
Image.fromarray(rgb8).save(sys.argv[3],quality=98,subsampling=0,icc_profile=icc)
print(json.dumps({'python':sys.version.split()[0],'numpy':np.__version__}))
'''
    completed = subprocess.run([python, '-B', '-c', code, str(adapter.parent), str(master), str(jpeg)],
                               check=True, capture_output=True, text=True, timeout=180)
    intact = (sha256(master) == master_hash and sha256(Path(__file__)) == frozen['card_pipeline.py']
              and sha256(adapter) == frozen['local_tone_balance.py'])
    if not intact:
        raise ValueError('base master or JPEG exporter changed during execution')
    return {'frozen_unchanged': intact, 'implementation_sha256': frozen,
            'master_unchanged': True, 'jpeg_sha256': sha256(jpeg),
            'environment': json.loads(completed.stdout), 'metadata_policy': 'JPEG contains source ICC only'}


def run_from_base_master(args, theme_manifest, cards, mask_graph, postprocess_recipe):
    """Copy a verified master, optionally applying one admitted local recipe; never open RAW in Adobe."""
    if args.preview_only or ',' in args.candidates:
        raise ValueError('base master mode requires one candidate and full TIFF/replay outputs')
    gid, stem = args.candidates.split(':')
    intent = theme_manifest.get('intents', {}).get(gid, {})
    params = merge_geometry(resolve_params(cards, intent.get('overrides', {})), None)
    source = src_nef2(args, stem)
    source_hash = sha256(source)
    inventory = json.loads((PROJECT / args.inventory).read_text())
    inv_key = f'{args.raw_subdir}/{stem}{args.ext}' if args.raw_subdir else f'{stem}{args.ext}'
    if {f['path']: f['sha256'] for f in inventory['files']}.get(inv_key) != source_hash:
        raise ValueError('source hash mismatch with frozen inventory')
    base_path, base, base_master = validate_base_master(
        args.base_master_manifest, gid, stem, source_hash, params, mask_graph)
    base_manifest_hash = sha256(base_path)
    base_hash = sha256(base_master)
    run_dir, out_dir = PROJECT / 'runs' / args.run_id, PROJECT / args.out_dir
    master, replay, jpeg = out_dir / f'{gid}-{stem}.tif', run_dir / f'{gid}-{stem}-replay.tif', out_dir / f'{gid}-{stem}.jpg'
    manifest_path = out_dir / f'{gid}-{stem}.manifest.json'
    for path in (master, replay, jpeg, manifest_path):
        if path.exists() or path.is_symlink():
            raise ValueError(f'base master mode requires fresh output paths: {path}')
    for path in (run_dir, out_dir):
        path.mkdir(parents=True, exist_ok=True)
    shutil.copy2(base_master, master)
    shutil.copy2(base_master, replay)
    copy_evidence = None
    if postprocess_recipe:
        result = postprocess_candidate(master, replay, jpeg, postprocess_recipe, run_dir, f'{gid}-{stem}', args.raster_python)
    else:
        result = None
        copy_evidence = export_base_master_jpeg(master, jpeg, args.raster_python)
        if sha256(master) != base_hash or sha256(replay) != base_hash:
            raise ValueError('base-master-copy must preserve the complete TIFF bytes')
    source_ok, source_after, source_error = verify_frozen_hash(source, source_hash)
    inherited_intact = sha256(base_master) == base_hash and sha256(base_path) == base_manifest_hash
    gates = {'G0_source_integrity': source_ok,
             'G1_params_frozen': (result or copy_evidence)['frozen_unchanged'] and inherited_intact,
             'G2_replay_deterministic': tiff_strip_sha256(master) == tiff_strip_sha256(replay),
             'G3_k3_review': 'NOT_REVIEWED', 'G4_claude_review': 'NOT_REVIEWED',
             'G5_user_acceptance': 'NOT_REQUESTED'}
    passed = render_passed(gates, False)
    manifest = {
        'candidate_id': f'{args.out_dir}/{gid}', 'scene_group': gid, 'frame': stem,
        'theme': args.theme, 'intent': intent.get('statement', ''),
        'cards': [{'card_id': c['card_id'], 'version': c['version'], 'status': c['status'], 'sha256': c['_sha256']} for c in cards],
        'card_confirmation': 'user_confirmation_pending' if any(c['status'] == 'candidate' for c in cards) else 'frozen',
        'resolved_params': params, 'mask_graph_sha256': base.get('mask_graph_sha256'),
        'postprocess': result, 'base_copy': copy_evidence, 'operation_registry_ref': OPERATION_REGISTRY_REF,
        'source_sha256': source_hash, 'source_sha256_after': source_after,
        'base_master': {'manifest': str(base_path.relative_to(PROJECT)), 'manifest_sha256': base_manifest_hash,
                        'master_tiff': str(base_master.relative_to(PROJECT)), 'master_tiff_sha256': base_hash,
                        'unchanged': inherited_intact, 'inherited_gates': base['gates']},
        'master_tiff': str(master.relative_to(PROJECT)), 'master_tiff_sha256': sha256(master),
        'master_pixel_strip_sha256': tiff_strip_sha256(master),
        'viewing_jpeg': str(jpeg.relative_to(PROJECT)), 'viewing_jpeg_sha256': sha256(jpeg),
        'gates': gates, 'integrity_errors': [source_error] if source_error else [],
        'environment': {'python': platform.python_version(), 'execution': 'existing verified Adobe master; no Adobe rerender'},
        'transmission_facts': {'scope': 'this_pipeline_execution', 'external_transfer_mode': 'LOCAL_ONLY',
                               'external_transfers': [], 'claude_review': 'NOT_PERFORMED', 'k3_review': 'NOT_PERFORMED'},
        'candidate_state': 'ACTIVE', 'render_pass': passed, 'quality_acceptance_passed': False,
        'render_mode': 'verified_base_master_postprocess' if postprocess_recipe else 'base-master-copy',
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + '\n')
    evidence = {'run_id': args.run_id, 'render_mode': manifest['render_mode'], 'render_pass': passed,
                'quality_acceptance_passed': False, 'pass': False, 'results': [{'gid': gid, 'frame': stem, 'gates': gates}]}
    (run_dir / 'evidence.json').write_text(json.dumps(evidence, indent=1) + '\n')
    print(json.dumps(evidence, indent=1))
    return 0 if passed else 1


_REVIEW_EXECUTION_TICKET = None


def _review_ticket_call(command: str, payload: dict) -> dict:
    completed = subprocess.run(
        ["node", str(PROJECT / "darkroom" / "review-render.mjs"), command],
        input=json.dumps(payload), text=True, capture_output=True, cwd=PROJECT,
        timeout=60,
    )
    if completed.returncode:
        raise SystemExit(f"REFUSED: render ticket: {completed.stderr.strip()}")
    return json.loads(completed.stdout)


def main() -> int:
    global _REVIEW_EXECUTION_TICKET
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", required=True)
    ap.add_argument("--candidates", required=True,
                    help="comma list gid:frame, e.g. PHOTO:frame")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--preview-only", action="store_true",
                    help="JPEG preview only; master TIFF/replay remain unverified, so this is not a finished candidate")
    ap.add_argument("--allow-candidate", action="store_true",
                    help="permit candidate-status cards; manifest records user_confirmation_pending")
    # Never infer an authorized source or reuse a historical delivery directory.
    ap.add_argument("--out-dir", required=True, help="explicit candidate output directory")
    ap.add_argument("--album", required=True, help="explicit authorized source or staging root")
    ap.add_argument("--raw-subdir", required=True, help="relative source subdirectory; use '' for direct children")
    ap.add_argument("--ext", required=True, help="explicit RAW extension, including the dot")
    ap.add_argument("--inventory", required=True, help="frozen inventory for these exact sources")
    ap.add_argument("--raster-python", default=sys.executable,
                    help="local Python with NumPy/Pillow for an admitted raster recipe")
    ap.add_argument('--base-master-manifest',
                    help='apply only the local recipe to an existing source-bound G0/G1/G2-verified master')
    authorization = ap.add_mutually_exclusive_group()
    authorization.add_argument('--review-ticket', help='reserved review execution ticket')
    authorization.add_argument('--local-trial-plan', help='frozen single-source LOCAL_ONLY trial plan')
    ap.add_argument('--review-crop-plan', help='frozen integer JPEG crop; keeps uncropped RAW masters intact')
    ap.add_argument('--acr-geometry-plan', help='frozen native ACR crop/rotation on the RAW working copy')
    args = ap.parse_args()
    _REVIEW_EXECUTION_TICKET = None
    if not args.review_ticket and not args.local_trial_plan:
        raise SystemExit("REFUSED: --review-ticket or --local-trial-plan is required before reading photos or writing renders")
    if args.review_ticket or args.base_master_manifest or args.review_crop_plan:
        raise SystemExit('REFUSED: public alpha supports local RAW trials and native ACR geometry only')
    if args.review_ticket:
        _review_ticket_call('check-render', {'ticket': args.review_ticket, 'argv': sys.argv[1:]})
        _REVIEW_EXECUTION_TICKET = args.review_ticket
        return _render(args)
    sys.path.insert(0, str(PROJECT))
    from darkroom import local_trial
    plan = local_trial.begin(PROJECT, args.local_trial_plan, sys.argv[1:])
    try:
        result = _render(args)
    except BaseException:
        local_trial.finish(PROJECT, plan, 1)
        raise
    return local_trial.finish(PROJECT, plan, result)


def _render(args) -> int:
    acr_geometry = None
    if getattr(args, 'acr_geometry_plan', None):
        from darkroom.acr_geometry import validate_geometry_plan
        acr_geometry = validate_geometry_plan(json.loads((PROJECT / args.acr_geometry_plan).read_text()))
        if args.review_crop_plan or args.base_master_manifest or args.preview_only or ',' in args.candidates:
            raise SystemExit('REFUSED: native ACR geometry requires one direct full RAW render without JPEG crop')
    crop_plan = None
    if args.review_crop_plan:
        sys.path.insert(0, str(PROJECT / 'darkroom'))
        from review_crop import validate_crop_plan
        crop_plan = validate_crop_plan(json.loads((PROJECT / args.review_crop_plan).read_text()))
        if args.base_master_manifest:
            raise SystemExit('REFUSED: declared crop currently requires direct RAW render')

    theme_manifest_path = PROJECT / "knowledge" / "themes" / f"{args.theme}.manifest.json"
    if not theme_manifest_path.exists():
        raise SystemExit(f"REFUSED: theme manifest missing: {theme_manifest_path}")
    theme_manifest = json.loads(theme_manifest_path.read_text())
    cards = load_cards(theme_manifest, args.allow_candidate)
    mask_graph = resolve_mask_graph(cards)
    postprocess_recipe = resolve_postprocess_recipe(cards)
    if acr_geometry and postprocess_recipe:
        raise SystemExit('REFUSED: native ACR geometry with a raster recipe has not been admitted')
    if args.base_master_manifest:
        return run_from_base_master(args, theme_manifest, cards, mask_graph, postprocess_recipe)
    if postprocess_recipe:
        raise SystemExit('REFUSED: raster recipes are not included in public alpha')
    if postprocess_recipe and args.preview_only:
        raise SystemExit("REFUSED: local tone balancing requires full TIFF and replay")

    run_dir = PROJECT / "runs" / args.run_id
    out_dir = PROJECT / args.out_dir
    render_root = PROJECT / "staging" / "render"
    for d in (run_dir, out_dir, render_root):
        d.mkdir(parents=True, exist_ok=True)

    inventory = json.loads((PROJECT / args.inventory).read_text())
    frozen = {f["path"]: f["sha256"] for f in inventory["files"]}

    jsx_body = "var darkroomPreviousDialogs = app.displayDialogs;\ntry {\napp.displayDialogs = DialogModes.NO;\n"
    plan = []
    for spec in args.candidates.split(","):
        gid, stem = spec.split(":")
        intent = theme_manifest.get("intents", {}).get(gid, {})
        overrides = intent.get("overrides", {})
        raw_dir = Path(args.album) / args.raw_subdir if args.raw_subdir else Path(args.album)
        src_nef = raw_dir / f"{stem}{args.ext}"
        orientation = read_raw_orientation(src_nef) if acr_geometry else None
        params = merge_geometry(resolve_params(cards, overrides), acr_geometry, orientation)
        inv_key = f"{args.raw_subdir}/{stem}{args.ext}" if args.raw_subdir else f"{stem}{args.ext}"
        src_hash = sha256(src_nef)
        if src_hash != frozen[inv_key]:
            raise SystemExit(f"REFUSED: source hash mismatch for {stem}")
        vdir = render_root / f"{gid}-{args.theme}-{args.run_id}"
        vdir.mkdir(exist_ok=True)
        nef = vdir / f"{stem}{args.ext}"
        stage_raw(src_nef, nef, src_hash)
        xmp = vdir / f"{stem}.xmp"
        xmp.write_text(render_xmp_sidecar(params, mask_graph, raw_orientation=orientation), encoding="utf-8")
        frozen_xmp_hash = sha256(xmp)
        master = out_dir / f"{gid}-{stem}.tif"
        replay = run_dir / f"{gid}-{stem}-replay.tif"
        jpeg = out_dir / f"{gid}-{stem}.jpg"
        plan_outputs = ((jpeg, JSX_JPEG),) if args.preview_only else (
            (master, JSX_TIFF), (replay, JSX_TIFF), (jpeg, JSX_JPEG))
        for out, tpl in plan_outputs:
            jsx_body += render_document_jsx(nef, out, tpl, xmp.read_text(encoding="utf-8"))
        plan.append((gid, stem, src_hash, params, intent, xmp, frozen_xmp_hash, master, replay, jpeg))
    jsx_body += '} finally { app.displayDialogs = darkroomPreviousDialogs; }\n"DONE";\n'
    jsx_path = run_dir / "card-render.jsx"
    jsx_path.write_text(jsx_body)

    t0 = datetime.now(timezone.utc)
    environment = render_environment()
    run_jsx_file(jsx_path)
    postprocess_results = {}
    if postprocess_recipe:
        for gid, stem, _src_hash, _params, _intent, _xmp, _xmp_hash, master, replay, jpeg in plan:
            postprocess_results[gid] = postprocess_candidate(
                master, replay, jpeg, postprocess_recipe, run_dir,
                f"{gid}-{stem}", args.raster_python)
    wall = round((datetime.now(timezone.utc) - t0).total_seconds(), 1)

    results, all_render_pass, all_quality_pass = [], True, True
    for gid, stem, src_hash, params, intent, xmp, frozen_xmp_hash, master, replay, jpeg in plan:
        source_ok, source_after_hash, source_error = verify_frozen_hash(src_nef2(args, stem), src_hash)
        params_ok, xmp_after_hash, xmp_error = verify_frozen_hash(xmp, frozen_xmp_hash)
        working_ok, working_after_hash, working_error = (verify_frozen_hash(xmp.with_suffix(args.ext), src_hash)
                                                        if acr_geometry else (True, None, None))
        native_geometry = geometry_evidence(acr_geometry, master, replay, read_raw_orientation(src_nef2(args, stem))) if acr_geometry else None
        gates = {
            "G0_source_integrity": source_ok,
            "G1_params_frozen": params_ok,
            "G2_replay_deterministic": ("DEFERRED_PREVIEW_ROUND" if args.preview_only
                                        else tiff_strip_sha256(master) == tiff_strip_sha256(replay)),
            "G3_visual_review": "NOT_REVIEWED",
            "G4_independent_review": "NOT_REVIEWED",
            "G5_user_acceptance": "NOT_REQUESTED",
        }
        if gid in postprocess_results:
            gates["G1_params_frozen"] = params_ok and postprocess_results[gid]["frozen_unchanged"]
        if native_geometry:
            gates['G0_source_integrity'] = source_ok and working_ok
            gates['G6_native_geometry_dimensions'] = native_geometry['dimension_gate_passed']
        candidate_render_pass = render_passed(gates, args.preview_only)
        if native_geometry:
            candidate_render_pass = candidate_render_pass and native_geometry['dimension_gate_passed']
        quality_pass = all(value is True for value in gates.values())
        crop_result = None
        if crop_plan and candidate_render_pass:
            cropped = subprocess.run([
                args.raster_python, '-B', '-m', 'darkroom.review_crop',
                '--plan', str(PROJECT / args.review_crop_plan), '--input', str(jpeg),
                '--output', str(out_dir / f'{gid}-{stem}-crop.jpg'),
                '--review', str(out_dir / f'{gid}-{stem}-crop-review-1600.jpg'),
                '--evidence', str(out_dir / f'{gid}-{stem}-crop.json'),
            ], cwd=PROJECT, capture_output=True, text=True, check=True)
            crop_result = json.loads(cropped.stdout)
        manifest = {
            "candidate_id": f"{args.out_dir}/{gid}",
            "scene_group": gid, "frame": stem,
            "theme": args.theme,
            "intent": intent.get("statement", ""),
            "reference_roster": theme_manifest.get("roster_version", ""),
            "cards": [{"card_id": c["card_id"], "version": c["version"],
                       "status": c["status"], "sha256": c["_sha256"]} for c in cards],
            "card_confirmation": ("user_confirmation_pending"
                                  if any(c["status"] == "candidate" for c in cards) else "frozen"),
            "resolved_params": params,
            "mask_graph_sha256": None if mask_graph is None else mask_graph["graph_sha256"],
            "mask_transport_orientation": None if not acr_geometry or mask_graph is None else native_geometry['source_orientation'],
            "postprocess": postprocess_results.get(gid),
            "crop_derivative": crop_result,
            "acr_geometry": native_geometry,
            "operation_registry_ref": OPERATION_REGISTRY_REF,
            "source_sha256": src_hash,
            "source_sha256_after": source_after_hash,
            "working_raw_sha256_after": working_after_hash,
            "acr_params_xmp_sha256": frozen_xmp_hash,
            "acr_params_xmp_sha256_after": xmp_after_hash,
            "integrity_errors": [error for error in (source_error, xmp_error, working_error) if error],
            "master_tiff": None if args.preview_only else str(master.relative_to(PROJECT)),
            "master_tiff_sha256": None if args.preview_only else sha256(master),
            "master_pixel_strip_sha256": None if args.preview_only else tiff_strip_sha256(master),
            "viewing_jpeg": str(jpeg.relative_to(PROJECT)),
            "viewing_jpeg_sha256": sha256(jpeg),
            "gates": gates,
            "environment": environment,
            "transmission_facts": {
                "scope": "this_pipeline_execution",
                "external_transfer_mode": "LOCAL_ONLY",
                "external_transfers": [],
                "independent_review": "NOT_PERFORMED",
                "visual_review": "NOT_PERFORMED",
            },
            "candidate_state": "ACTIVE",
            "render_pass": candidate_render_pass,
            "quality_acceptance_passed": quality_pass,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        manifest["render_mode"] = "preview_only" if args.preview_only else "full"
        (out_dir / f"{gid}-{stem}.manifest.json").write_text(
            json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
        all_render_pass = all_render_pass and candidate_render_pass
        all_quality_pass = all_quality_pass and quality_pass
        results.append({"gid": gid, "frame": stem, "gates": gates,
                        "render_pass": candidate_render_pass,
                        "quality_acceptance_passed": quality_pass})

    evidence = {"run_id": args.run_id, "theme": args.theme, "wall_seconds": wall,
                "operation_registry_ref": OPERATION_REGISTRY_REF,
                "mask_graph_sha256": None if mask_graph is None else mask_graph["graph_sha256"],
                "cards": [c["card_id"] for c in cards], "results": results,
                "render_pass": all_render_pass, "quality_acceptance_passed": all_quality_pass,
                "pass": all_quality_pass}
    (run_dir / "evidence.json").write_text(json.dumps(evidence, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(evidence, indent=1, ensure_ascii=False))
    return 0 if all_render_pass else 1


if __name__ == "__main__":
    try:
        _exit_code = main()
    except BaseException:
        if _REVIEW_EXECUTION_TICKET:
            try:
                _review_ticket_call('finish-render', {'ticket': _REVIEW_EXECUTION_TICKET, 'exitCode': 1})
            except BaseException as _receipt_error:
                print(f"REFUSED: render failure receipt could not be recorded: {_receipt_error}", file=sys.stderr)
        raise
    else:
        if _REVIEW_EXECUTION_TICKET:
            _review_ticket_call('finish-render', {'ticket': _REVIEW_EXECUTION_TICKET, 'exitCode': _exit_code})
        sys.exit(_exit_code)
