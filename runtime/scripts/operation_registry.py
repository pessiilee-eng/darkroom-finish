#!/usr/bin/env python3
"""Load the Adobe operation registry and enforce card admission semantics."""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, localcontext
from html import unescape
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT / "registries" / "adobe-operation-registry-v1.json"
SCHEMA_PATH = PROJECT / "schemas" / "adobe-operation-registry-v1.schema.json"
SCHEMA_ID = "https://darkroom-finish.local/schemas/adobe-operation-registry-v1.schema.json"
EVIDENCE_STAGES = (
    "documented",
    "schema_representable",
    "executor_write",
    "executor_readback",
    "fixture_probe",
    "replay",
)
MASK_OPERATION_IDS = {
    "brush": "acr.brush_mask",
    "linear_gradient": "acr.linear_gradient_mask",
    "radial_gradient": "acr.radial_gradient_mask",
    "color_range": "acr.color_range_mask",
    "luminance_range": "acr.luminance_range_mask",
}
IMPLEMENTED_TRANSPORT_KINDS = frozenset({"xmp_attribute", "xmp_rdf_seq", "xmp_mask_graph", "local_raster_recipe"})
LOCAL_TONE_OPERATION_ID = "local.harmonic_tone_balance"
LOCAL_SKIN_OPERATION_ID = "local.skin_control_field"
LOCAL_TEXTURE_OPERATION_ID = "local.skin_texture_smoothing"
LOCAL_SUN_GLOW_OPERATION_ID = "local.sun_glow"
LOCAL_SAMPLED_REPAIR_OPERATION_ID = "local.sampled_frequency_repair"
LOCAL_SAME_SOURCE_RESTORE_OPERATION_ID = "local.same_source_restore"
LOCAL_TONAL_BRUSH_OPERATION_ID = "local.tonal_brush"
LOCAL_SPATIAL_LIGHT_OPERATION_ID = "local.spatial_light"
LOCAL_SAME_IMAGE_CLONE_OPERATION_ID = "local.same_image_clone"
LOCAL_RECIPE_TRANSPORT_KEYS = {
    LOCAL_TONE_OPERATION_ID: "HarmonicToneBalance",
    LOCAL_SKIN_OPERATION_ID: "SkinControlField",
    LOCAL_TEXTURE_OPERATION_ID: "SkinTextureSmoothing",
    LOCAL_SUN_GLOW_OPERATION_ID: "SunGlow",
    LOCAL_SAMPLED_REPAIR_OPERATION_ID: "SampledFrequencyRepair",
    LOCAL_SAME_SOURCE_RESTORE_OPERATION_ID: "SameSourceRestore",
    LOCAL_TONAL_BRUSH_OPERATION_ID: "TonalBrush",
    LOCAL_SPATIAL_LIGHT_OPERATION_ID: "SpatialLight",
    LOCAL_SAME_IMAGE_CLONE_OPERATION_ID: "SameImageClone",
}
LOCAL_RECIPE_SCHEMAS = {
    LOCAL_TONE_OPERATION_ID: "local-tone-balance/v1",
    LOCAL_SKIN_OPERATION_ID: "local-skin-field/v1",
    LOCAL_TEXTURE_OPERATION_ID: "local-skin-texture/v1",
    LOCAL_SUN_GLOW_OPERATION_ID: "local-sun-glow/v1",
    LOCAL_SAMPLED_REPAIR_OPERATION_ID: "local-sampled-repair/v1",
    LOCAL_SAME_SOURCE_RESTORE_OPERATION_ID: "local-same-source-restore/v1",
    LOCAL_TONAL_BRUSH_OPERATION_ID: "local-tonal-brush/v1",
    LOCAL_SPATIAL_LIGHT_OPERATION_ID: "local-spatial-light/v1",
    LOCAL_SAME_IMAGE_CLONE_OPERATION_ID: "local-same-image-clone/v1",
}
MASK_LOCAL_FIELDS = {
    # mask_graph/v1 stores native LocalExposure2012, not global/UI EV.
    # Native local scale, not the global/UI exposure scale.
    "exposure2012": ("LocalExposure2012", Decimal("-1"), Decimal("1")),
    "contrast2012": ("LocalContrast2012", Decimal("-100"), Decimal("100")),
    "highlights2012": ("LocalHighlights2012", Decimal("-100"), Decimal("100")),
    "shadows2012": ("LocalShadows2012", Decimal("-100"), Decimal("100")),
    "whites2012": ("LocalWhites2012", Decimal("-100"), Decimal("100")),
    "blacks2012": ("LocalBlacks2012", Decimal("-100"), Decimal("100")),
    "clarity2012": ("LocalClarity2012", Decimal("-100"), Decimal("100")),
    "dehaze": ("LocalDehaze", Decimal("-100"), Decimal("100")),
    "temperature": ("LocalTemperature", Decimal("-100"), Decimal("100")),
    "tint": ("LocalTint", Decimal("-100"), Decimal("100")),
    "texture": ("LocalTexture", Decimal("-100"), Decimal("100")),
    "saturation": ("LocalSaturation", Decimal("-100"), Decimal("100")),
    "sharpness": ("LocalSharpness", Decimal("-100"), Decimal("100")),
}
ENUM_TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
DECIMAL_STRING_RE = re.compile(r"^(0|[1-9][0-9]*|-[1-9][0-9]*|-?(0|[1-9][0-9]*)\.[0-9]*[1-9])$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
EXPLICIT_HTML_ANCHOR_RE = re.compile(r"<a\s+(?:[^>]*?\s+)?(?:id|name)=[\"']([^\"']+)[\"']", re.IGNORECASE)


class OperationRegistryError(ValueError):
    """The checked-in operation registry is structurally or semantically invalid."""


def canonical_sha256(value: Any) -> str:
    """Hash the project's restricted canonical JSON representation."""

    sys.path.insert(0, str(PROJECT / "scripts"))
    from verify_ai_darkroom_contracts import sha256_jcs  # noqa: E402

    return sha256_jcs(value)


def operation_registry_ref(registry: dict[str, Any]) -> dict[str, str]:
    return {
        "registry_id": registry["registry_id"],
        "version": registry["version"],
        "sha256": registry["registry_sha256"],
    }


def _markdown_anchors(text: str) -> set[str]:
    """Return explicit HTML anchors plus the common GitHub heading slugs."""

    anchors = set(EXPLICIT_HTML_ANCHOR_RE.findall(text))
    for line in text.splitlines():
        match = MARKDOWN_HEADING_RE.match(line)
        if match is None:
            continue
        heading = unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip().lower()
        heading = re.sub(r"[^\w\- ]", "", heading, flags=re.UNICODE)
        anchors.add(re.sub(r"\s+", "-", heading))
    return anchors


def _local_evidence_ref_error(evidence_ref: str) -> str | None:
    """Fail closed for project-local evidence paths and Markdown anchors."""

    if evidence_ref.startswith(("https://", "http://")):
        return None
    if "#" in evidence_ref:
        path_text, anchor = evidence_ref.split("#", 1)
    else:
        path_text, anchor = evidence_ref, ""
    if not anchor:
        return f"evidence_ref requires an explicit local anchor: {evidence_ref}"
    path = (PROJECT / path_text).resolve(strict=False)
    try:
        path.relative_to(PROJECT.resolve())
    except ValueError:
        return f"evidence_ref escapes project: {evidence_ref}"
    if not path.is_file():
        return f"evidence_ref path missing: {evidence_ref}"
    if anchor:
        if path.suffix.lower() != ".md":
            return f"evidence_ref anchor requires Markdown: {evidence_ref}"
        if anchor not in _markdown_anchors(path.read_text(encoding="utf-8")):
            return f"evidence_ref anchor missing: {evidence_ref}"
    return None


def _registry_semantic_errors(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if tuple(registry.get("promotion_requirements", ())) != EVIDENCE_STAGES:
        errors.append("promotion_requirements must contain all evidence stages in canonical order")

    registry_preimage = dict(registry)
    claimed_registry_hash = registry_preimage.pop("registry_sha256", None)
    if claimed_registry_hash is None or canonical_sha256(registry_preimage) != claimed_registry_hash:
        errors.append("registry_sha256 does not match canonical registry content")

    enum_domains: dict[tuple[str, str, str], dict[str, Any]] = {}
    for domain in registry.get("enum_domains", []):
        domain_preimage = dict(domain)
        claimed_domain_hash = domain_preimage.pop("registry_sha256", None)
        if claimed_domain_hash is None or canonical_sha256(domain_preimage) != claimed_domain_hash:
            errors.append(f"enum domain hash mismatch: {domain.get('registry_id')}")
            continue
        values = domain["values"]
        native_values = domain["native_values"]
        if (
            values != sorted(values, key=lambda value: value.encode("utf-8"))
            or any(not ENUM_TOKEN_RE.fullmatch(value) for value in values)
            or set(native_values) != set(values)
            or len(set(native_values.values())) != len(native_values)
        ):
            errors.append(f"invalid enum domain values: {domain['registry_id']}")
        key = (domain["registry_id"], domain["version"], claimed_domain_hash)
        if key in enum_domains:
            errors.append(f"duplicate enum domain: {domain['registry_id']}@{domain['version']}")
        enum_domains[key] = domain

    seen_ids: set[str] = set()
    seen_fields: set[str] = set()
    seen_transport_keys: dict[str, str] = {}
    for operation in registry.get("operations", []):
        operation_id = operation["operation_id"]
        field = operation["field"]
        if operation_id in seen_ids:
            errors.append(f"duplicate operation_id: {operation_id}")
        seen_ids.add(operation_id)
        if field is not None:
            if field in seen_fields:
                errors.append(f"duplicate field: {field}")
            seen_fields.add(field)

        evidence = operation["evidence"]
        for stage in EVIDENCE_STAGES:
            item = evidence[stage]
            if item["status"] == "supported" and item["evidence_ref"] is None:
                errors.append(f"{operation_id}.{stage} is supported without evidence_ref")
            if item["evidence_ref"] is not None:
                ref_error = _local_evidence_ref_error(item["evidence_ref"])
                if ref_error is not None:
                    errors.append(f"{operation_id}.{stage} {ref_error}")

        write_supported = evidence["executor_write"]["status"] == "supported"
        if write_supported and operation["transport"] is None:
            errors.append(f"{operation_id} claims executor_write without field/transport")
        if write_supported and any(
            evidence[stage]["status"] != "supported"
            for stage in ("documented", "schema_representable")
        ):
            errors.append(f"{operation_id} executor_write lacks documented/schema support")
        transport = operation["transport"]
        if operation_id in LOCAL_RECIPE_TRANSPORT_KEYS or operation["product"] == "local_raster" or (
            transport is not None and transport["kind"] == "local_raster_recipe"
        ):
            if (
                operation_id not in LOCAL_RECIPE_TRANSPORT_KEYS
                or operation["product"] != "local_raster"
                or field is not None
                or operation["value_type"] != "action"
                or operation["native_unit"] is not None
                or operation["native_range"] is not None
                or operation["scope"] != "local"
                or transport != {"kind": "local_raster_recipe", "key": LOCAL_RECIPE_TRANSPORT_KEYS.get(operation_id)}
            ):
                errors.append(f"{operation_id} invalid local raster recipe semantics")
        if write_supported and transport is not None:
            if transport["kind"] not in IMPLEMENTED_TRANSPORT_KINDS:
                errors.append(
                    f"{operation_id} executor_write uses unimplemented transport: {transport['kind']}"
                )
            transport_keys = [transport["key"], *transport.get("companion_attributes", {})]
            if not transport.get("companion_attributes", {"_": "_"}):
                errors.append(f"{operation_id} has empty companion_attributes")
            for transport_key in transport_keys:
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", transport_key):
                    errors.append(f"{operation_id} has invalid XMP transport key: {transport_key}")
                previous_kind = seen_transport_keys.get(transport_key)
                if previous_kind is not None and not (
                    previous_kind == "xmp_mask_graph" and transport["kind"] == "xmp_mask_graph"
                ):
                    errors.append(f"duplicate executable transport key: {transport_key}")
                seen_transport_keys[transport_key] = transport["kind"]
            if transport["kind"] == "xmp_rdf_seq" and operation["value_type"] != "curve":
                errors.append(f"{operation_id} RDF sequence transport requires curve value_type")
            if operation["value_type"] == "curve" and transport["kind"] != "xmp_rdf_seq":
                errors.append(f"{operation_id} executable curve requires xmp_rdf_seq transport")
            if operation["value_type"] == "mask_graph" and (
                field is not None or transport["kind"] != "xmp_mask_graph"
            ):
                errors.append(f"{operation_id} executable mask requires xmp_mask_graph transport")
            if transport.get("companion_attributes") and transport["kind"] != "xmp_rdf_seq":
                errors.append(f"{operation_id} companion_attributes require xmp_rdf_seq transport")
        if operation["charter_class"] == "prohibited" and write_supported:
            errors.append(f"{operation_id} is prohibited but claims executor_write")
        if operation["value_type"] in {"scalar", "enum", "curve"}:
            if field is None or operation["native_unit"] is None:
                errors.append(f"{operation_id} lacks scalar/enum/curve field semantics")
        if operation["value_type"] == "scalar" and operation["native_range"] is None:
            errors.append(f"{operation_id} scalar lacks native_range")
        if operation["value_type"] == "curve" and operation["native_range"] is not None:
            errors.append(f"{operation_id} curve must not declare a scalar native_range")
        domain_ref = operation["enum_domain_ref"]
        if operation["value_type"] == "enum":
            if domain_ref is None:
                errors.append(f"{operation_id} enum lacks enum_domain_ref")
            elif (domain_ref["registry_id"], domain_ref["version"], domain_ref["sha256"]) not in enum_domains:
                errors.append(f"{operation_id} enum_domain_ref is unknown")
        elif domain_ref is not None:
            errors.append(f"{operation_id} non-enum has enum_domain_ref")
        native_range = operation["native_range"]
        if native_range is not None and Decimal(native_range["lower"]) > Decimal(native_range["upper"]):
            errors.append(f"{operation_id} native_range is reversed")

        supported = {stage for stage in EVIDENCE_STAGES if evidence[stage]["status"] == "supported"}
        if "executor_readback" in supported and "executor_write" not in supported:
            errors.append(f"{operation_id} readback support lacks write support")
        if "fixture_probe" in supported and not {"executor_write", "executor_readback"} <= supported:
            errors.append(f"{operation_id} fixture proof lacks write/readback support")
        if "replay" in supported and not set(EVIDENCE_STAGES[:-1]) <= supported:
            errors.append(f"{operation_id} replay proof lacks prerequisite evidence")
    return errors


def load_operation_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """Load, JSON-Schema validate, and semantically validate the registry."""

    sys.path.insert(0, str(PROJECT / "scripts"))
    from verify_ai_darkroom_contracts import (  # noqa: E402
        LocalDraft202012Validator,
        SCHEMA_PATHS,
        SchemaValidationError,
    )

    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
        schema_paths = {**SCHEMA_PATHS, "operation": SCHEMA_PATH}
        schemas = {
            name: json.loads(schema_path.read_text(encoding="utf-8"))
            for name, schema_path in schema_paths.items()
        }
        validator = LocalDraft202012Validator(schemas)
        validator.validate(registry, schemas["operation"], base_uri=SCHEMA_ID)
    except (OSError, json.JSONDecodeError, AssertionError, SchemaValidationError) as exc:
        raise OperationRegistryError(f"invalid Adobe operation registry: {exc}") from exc

    errors = _registry_semantic_errors(registry)
    if errors:
        raise OperationRegistryError("invalid Adobe operation registry: " + "; ".join(errors))
    return registry


def operations_by_id(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {operation["operation_id"]: operation for operation in registry["operations"]}


def operations_by_field(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        operation["field"]: operation
        for operation in registry["operations"]
        if operation["field"] is not None
    }


def field_to_xmp_mapping(registry: dict[str, Any] | None = None) -> dict[str, str]:
    """Return the current XMP write surface directly from registry evidence."""

    return {
        field: transport["key"]
        for field, transport in field_to_xmp_transport_mapping(registry).items()
    }


def field_to_xmp_transport_mapping(
    registry: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return executable field -> transport mappings from registry evidence."""

    registry = registry or load_operation_registry()
    result: dict[str, dict[str, Any]] = {}
    for operation in registry["operations"]:
        transport = operation["transport"]
        if (
            operation["field"] is not None
            and operation["charter_class"] != "prohibited"
            and operation["evidence"]["executor_write"]["status"] == "supported"
            and transport is not None
            and transport["kind"] in {"xmp_attribute", "xmp_rdf_seq"}
        ):
            result[operation["field"]] = dict(transport)
    return dict(sorted(result.items()))


def enum_domain_for_operation(
    operation: dict[str, Any], registry: dict[str, Any]
) -> dict[str, Any] | None:
    domain_ref = operation["enum_domain_ref"]
    if domain_ref is None:
        return None
    for domain in registry["enum_domains"]:
        candidate_ref = {
            "registry_id": domain["registry_id"],
            "version": domain["version"],
            "sha256": domain["registry_sha256"],
        }
        if candidate_ref == domain_ref:
            return domain
    return None


def native_parameter_value(
    field: str, scalar: dict[str, Any], registry: dict[str, Any] | None = None
) -> str | list[str]:
    """Translate a canonical parameter value into its native XMP representation."""

    registry = registry or load_operation_registry()
    operation = operations_by_field(registry).get(field)
    if operation is None:
        raise OperationRegistryError(f"unknown executable field: {field}")
    if scalar["type"] == "curve":
        if operation["value_type"] != "curve":
            raise OperationRegistryError(f"curve value supplied to non-curve field: {field}")
        points = scalar.get("points")
        if not isinstance(points, list) or len(points) < 2:
            raise OperationRegistryError(f"curve requires at least two points: {field}")
        native_points: list[str] = []
        previous_input: int | None = None
        for index, point in enumerate(points):
            try:
                input_value = int(point["input"])
                output_value = int(point["output"])
            except (KeyError, TypeError, ValueError) as exc:
                raise OperationRegistryError(
                    f"curve point is not an integer pair: {field}:index={index}"
                ) from exc
            if not 0 <= input_value <= 255 or not 0 <= output_value <= 255:
                raise OperationRegistryError(
                    f"curve point outside 0..255: {field}:index={index}"
                )
            if previous_input is not None and input_value <= previous_input:
                raise OperationRegistryError(
                    f"curve inputs must be strictly increasing: {field}:index={index}"
                )
            previous_input = input_value
            native_points.append(f"{input_value}, {output_value}")
        if int(points[0]["input"]) != 0 or int(points[-1]["input"]) != 255:
            raise OperationRegistryError(f"curve must span input endpoints 0 and 255: {field}")
        return native_points
    if operation["value_type"] == "curve":
        raise OperationRegistryError(f"non-curve value supplied to curve field: {field}")
    if scalar["type"] != "enum":
        return str(scalar["value"])
    domain_ref = operation["enum_domain_ref"]
    if scalar.get("domain_ref") != domain_ref:
        raise OperationRegistryError(f"enum domain mismatch: {field}")
    domain = enum_domain_for_operation(operation, registry)
    token = scalar["value"]
    if domain is None or token not in domain["native_values"]:
        raise OperationRegistryError(f"unknown enum token: {field}:{token}")
    return domain["native_values"][token]


def _inside(value: Decimal, range_spec: dict[str, str]) -> bool:
    lower = Decimal(range_spec["lower"])
    upper = Decimal(range_spec["upper"])
    inclusivity = range_spec["inclusivity"]
    lower_ok = value >= lower if inclusivity in {"closed", "left_closed"} else value > lower
    upper_ok = value <= upper if inclusivity in {"closed", "right_closed"} else value < upper
    return lower_ok and upper_ok


def _rule_unit(value_spec: dict[str, Any]) -> str:
    if value_spec["kind"] == "absolute":
        return value_spec["unit"]
    return value_spec["formula"]["result_unit"]


def _admission_errors(operation: dict[str, Any], status: str, subject: str) -> list[str]:
    errors: list[str] = []
    if operation["charter_class"] == "prohibited":
        errors.append(f"PROHIBITED_OPERATION:{subject}")
        return errors
    evidence = operation["evidence"]
    if status == "candidate" and evidence["executor_write"]["status"] != "supported":
        errors.append(f"CANDIDATE_NOT_EXECUTABLE:{subject}")
    if status == "frozen":
        missing = [stage for stage in EVIDENCE_STAGES if evidence[stage]["status"] != "supported"]
        if missing:
            errors.append(f"FROZEN_PROMOTION_EVIDENCE_MISSING:{subject}:{','.join(missing)}")
    return errors


def _mask_graph_errors(graph: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(graph, dict):
        return ["MASK_GRAPH_NOT_OBJECT"]
    if graph.get("schema_version") != "mask_graph/v1":
        errors.append("MASK_GRAPH_VERSION_MISMATCH")
    if graph.get("coordinate_space") != "normalized_upright":
        errors.append("MASK_COORDINATE_SPACE_MISMATCH")
    expected_keys = {"schema_version", "coordinate_space", "groups", "graph_sha256"}
    if set(graph) != expected_keys:
        errors.append("MASK_GRAPH_KEYS_INVALID")
    groups = graph.get("groups")
    if not isinstance(groups, list) or not 1 <= len(groups) <= 32:
        errors.append("MASK_GROUPS_INVALID")
        return errors
    preimage = dict(graph)
    claimed_hash = preimage.pop("graph_sha256", None)
    if claimed_hash is None or canonical_sha256(preimage) != claimed_hash:
        errors.append("MASK_GRAPH_HASH_MISMATCH")

    seen_ids: set[str] = set()
    orders: list[int] = []

    def decimal_in(value: str, lower: Decimal, upper: Decimal, subject: str) -> Decimal | None:
        if not isinstance(value, str) or len(value) > 64 or not DECIMAL_STRING_RE.fullmatch(value):
            errors.append(f"MASK_INVALID_DECIMAL:{subject}")
            return None
        try:
            parsed = Decimal(value)
        except Exception:
            errors.append(f"MASK_INVALID_DECIMAL:{subject}")
            return None
        if not lower <= parsed <= upper:
            errors.append(f"MASK_RANGE_MISMATCH:{subject}:value={value}")
        return parsed

    def unique_id(value: str, subject: str) -> None:
        if not IDENTIFIER_RE.fullmatch(value):
            errors.append(f"MASK_INVALID_ID:{subject}:{value}")
        if value in seen_ids:
            errors.append(f"MASK_DUPLICATE_ID:{value}")
        seen_ids.add(value)

    for group in groups:
        if not isinstance(group, dict):
            errors.append("MASK_GROUP_NOT_OBJECT")
            continue
        required_group_keys = {"id", "name", "operation_order", "local_adjustments", "masks"}
        if set(group) != required_group_keys:
            errors.append(f"MASK_GROUP_KEYS_INVALID:{group.get('id', '<missing>')}")
            continue
        if (not isinstance(group["id"], str) or not isinstance(group["name"], str)
                or not 1 <= len(group["name"]) <= 80):
            errors.append("MASK_GROUP_IDENTITY_INVALID")
            continue
        if not isinstance(group["operation_order"], int) or group["operation_order"] < 0:
            errors.append(f"MASK_GROUP_ORDER_INVALID:{group['id']}")
            continue
        if not isinstance(group["local_adjustments"], dict):
            errors.append(f"MASK_LOCAL_ADJUSTMENTS_INVALID:{group['id']}")
            continue
        if not isinstance(group["masks"], list) or not 1 <= len(group["masks"]) <= 32:
            errors.append(f"MASKS_INVALID:{group['id']}")
            continue
        unique_id(group["id"], "group")
        orders.append(group["operation_order"])
        for field, value in group["local_adjustments"].items():
            contract = MASK_LOCAL_FIELDS.get(field)
            if contract is None:
                errors.append(f"MASK_UNKNOWN_LOCAL_FIELD:{field}")
            else:
                decimal_in(value, contract[1], contract[2], f"{group['id']}.{field}")
        luminance_count = 0
        for mask in group["masks"]:
            if not isinstance(mask, dict) or not isinstance(mask.get("id"), str):
                errors.append(f"MASK_PRIMITIVE_INVALID:{group['id']}")
                continue
            unique_id(mask["id"], "mask")
            mask_type = mask.get("type")
            if mask.get("composition") != "add":
                errors.append(f"MASK_UNSUPPORTED_COMPOSITION:{mask['id']}")
            if mask_type == "brush":
                if set(mask) != {"id", "type", "composition", "dabs"}:
                    errors.append(f"MASK_PRIMITIVE_KEYS_INVALID:{mask['id']}")
                    continue
                if not isinstance(mask["dabs"], list) or not mask["dabs"]:
                    errors.append(f"MASK_EMPTY_BRUSH:{mask['id']}")
                    continue
                for index, dab in enumerate(mask["dabs"]):
                    prefix = f"{mask['id']}.dabs[{index}]"
                    if not isinstance(dab, dict) or set(dab) != {"x", "y", "radius", "flow", "feather"}:
                        errors.append(f"MASK_DAB_INVALID:{prefix}")
                        continue
                    decimal_in(dab["x"], Decimal("0"), Decimal("1"), f"{prefix}.x")
                    decimal_in(dab["y"], Decimal("0"), Decimal("1"), f"{prefix}.y")
                    radius = decimal_in(
                        dab["radius"], Decimal("0"), Decimal("1"), f"{prefix}.radius"
                    )
                    if radius == 0:
                        errors.append(f"MASK_ZERO_RADIUS:{prefix}")
                    flow = decimal_in(dab["flow"], Decimal("0"), Decimal("1"), f"{prefix}.flow")
                    if flow == 0:
                        errors.append(f"MASK_ZERO_FLOW:{prefix}")
                    decimal_in(dab["feather"], Decimal("0"), Decimal("1"), f"{prefix}.feather")
            elif mask_type == "linear_gradient":
                if set(mask) != {"id", "type", "composition", "start", "end"}:
                    errors.append(f"MASK_PRIMITIVE_KEYS_INVALID:{mask['id']}")
                    continue
                for endpoint in ("start", "end"):
                    if not isinstance(mask[endpoint], dict) or set(mask[endpoint]) != {"x", "y"}:
                        errors.append(f"MASK_POINT_INVALID:{mask['id']}.{endpoint}")
                        continue
                    decimal_in(mask[endpoint]["x"], Decimal("0"), Decimal("1"), f"{mask['id']}.{endpoint}.x")
                    decimal_in(mask[endpoint]["y"], Decimal("0"), Decimal("1"), f"{mask['id']}.{endpoint}.y")
                if mask["start"] == mask["end"]:
                    errors.append(f"MASK_DEGENERATE_LINEAR:{mask['id']}")
            elif mask_type == "radial_gradient":
                if set(mask) != {"id", "type", "composition", "center", "radius_x", "radius_y", "angle_degrees", "feather", "inverted"}:
                    errors.append(f"MASK_PRIMITIVE_KEYS_INVALID:{mask['id']}")
                    continue
                if not isinstance(mask["center"], dict) or set(mask["center"]) != {"x", "y"}:
                    errors.append(f"MASK_POINT_INVALID:{mask['id']}.center")
                    continue
                if not isinstance(mask["inverted"], bool):
                    errors.append(f"MASK_INVERTED_INVALID:{mask['id']}")
                decimal_in(mask["center"]["x"], Decimal("0"), Decimal("1"), f"{mask['id']}.center.x")
                decimal_in(mask["center"]["y"], Decimal("0"), Decimal("1"), f"{mask['id']}.center.y")
                for radius_name in ("radius_x", "radius_y"):
                    radius = decimal_in(mask[radius_name], Decimal("0"), Decimal("1"), f"{mask['id']}.{radius_name}")
                    if radius == 0:
                        errors.append(f"MASK_ZERO_RADIUS:{mask['id']}.{radius_name}")
                decimal_in(mask["angle_degrees"], Decimal("-180"), Decimal("180"), f"{mask['id']}.angle_degrees")
                decimal_in(mask["feather"], Decimal("0"), Decimal("1"), f"{mask['id']}.feather")
            elif mask_type == "luminance_range":
                if set(mask) != {"id", "type", "composition", "minimum", "maximum", "feather"}:
                    errors.append(f"MASK_PRIMITIVE_KEYS_INVALID:{mask['id']}")
                    continue
                luminance_count += 1
                minimum = decimal_in(mask["minimum"], Decimal("0"), Decimal("1"), f"{mask['id']}.minimum")
                maximum = decimal_in(mask["maximum"], Decimal("0"), Decimal("1"), f"{mask['id']}.maximum")
                decimal_in(mask["feather"], Decimal("0"), Decimal("1"), f"{mask['id']}.feather")
                if minimum is not None and maximum is not None and minimum >= maximum:
                    errors.append(f"MASK_LUMINANCE_RANGE_REVERSED:{mask['id']}")
            else:
                errors.append(f"MASK_UNSUPPORTED_SELECTOR:{mask_type}")
        if luminance_count > 1:
            errors.append(f"MASK_MULTIPLE_LUMINANCE_RANGES:{group['id']}")
    if orders != sorted(orders) or len(orders) != len(set(orders)):
        errors.append("MASK_GROUP_ORDER_INVALID")
    return errors


def validate_mask_graph(graph: dict[str, Any]) -> None:
    """Fail closed unless a mask_graph/v1 is canonical and executable."""

    errors = _mask_graph_errors(graph)
    if errors:
        raise OperationRegistryError("invalid mask graph: " + "; ".join(errors))


def postprocess_recipe_sha256(recipe: dict[str, Any]) -> str:
    """Hash a local postprocess recipe, excluding its self-hash field."""

    preimage = dict(recipe)
    preimage.pop("recipe_sha256", None)
    return canonical_sha256(preimage)


def _sun_glow_region_errors(regions, errors, decimal_in):
    """An independent compact-glow contract; no changes to skin/tone bounds."""
    if len(regions) > 2:
        errors.append("POSTPROCESS_SUN_REGIONS_INVALID")
    seen_ids = set()

    def identifier(value, subject):
        if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
            errors.append(f"POSTPROCESS_INVALID_ID:{subject}")
        elif value in seen_ids:
            errors.append(f"POSTPROCESS_DUPLICATE_ID:{value}")
        else:
            seen_ids.add(value)

    def pair(value, names, lower, upper, subject):
        if not isinstance(value, dict) or set(value) != set(names):
            errors.append(f"POSTPROCESS_SUN_PAIR_INVALID:{subject}")
            return
        for name in names:
            decimal_in(value[name], lower, upper, f"{subject}.{name}")

    for index, region in enumerate(regions):
        subject = f"regions[{index}]"
        if not isinstance(region, dict) or set(region) != {'id', 'center', 'support', 'lobes', 'protections'}:
            errors.append(f"POSTPROCESS_REGION_KEYS_INVALID:{subject}")
            continue
        identifier(region['id'], subject)
        pair(region['center'], ('x', 'y'), '0', '1', f'{subject}.center')
        pair(region['support'], ('rx', 'ry'), '0.01', '0.6', f'{subject}.support')
        lobes = region['lobes']
        if not isinstance(lobes, list) or not 2 <= len(lobes) <= 4:
            errors.append(f'POSTPROCESS_SUN_LOBES_INVALID:{subject}')
        else:
            scales = []
            for j, lobe in enumerate(lobes):
                item = f'{subject}.lobes[{j}]'
                if not isinstance(lobe, dict) or set(lobe) != {'id', 'radius_scale', 'opacity', 'color'}:
                    errors.append(f'POSTPROCESS_SUN_LOBE_KEYS_INVALID:{item}')
                    continue
                identifier(lobe['id'], item)
                scale = decimal_in(lobe['radius_scale'], '0.03', '1', f'{item}.radius_scale')
                if scale is not None: scales.append(scale)
                decimal_in(lobe['opacity'], '0', '0.8', f'{item}.opacity')
                color = lobe['color']
                if not isinstance(color, dict) or set(color) != {'r', 'g', 'b'}:
                    errors.append(f'POSTPROCESS_SUN_COLOR_INVALID:{item}')
                else:
                    channels = [decimal_in(color[k], '0', '1', f'{item}.color.{k}') for k in ('r', 'g', 'b')]
                    if all(c is not None for c in channels) and not channels[0] >= channels[1] >= channels[2]:
                        errors.append(f'POSTPROCESS_SUN_COLOR_NOT_WARM:{item}')
            if len(scales) == len(lobes) and (scales != sorted(scales) or len(set(scales)) != len(scales)):
                errors.append(f'POSTPROCESS_SUN_LOBE_SCALE_ORDER_INVALID:{subject}')
        protections = region['protections']
        if not isinstance(protections, list) or len(protections) > 4:
            errors.append(f'POSTPROCESS_SUN_PROTECTIONS_INVALID:{subject}')
        else:
            for j, protection in enumerate(protections):
                item = f'{subject}.protections[{j}]'
                if not isinstance(protection, dict) or set(protection) != {'id', 'center', 'radius', 'strength', 'feather'}:
                    errors.append(f'POSTPROCESS_SUN_PROTECTION_KEYS_INVALID:{item}')
                    continue
                identifier(protection['id'], item)
                pair(protection['center'], ('x', 'y'), '0', '1', f'{item}.center')
                pair(protection['radius'], ('rx', 'ry'), '0.005', '0.5', f'{item}.radius')
                decimal_in(protection['strength'], '0', '1', f'{item}.strength')
                decimal_in(protection['feather'], '0.05', '1', f'{item}.feather')
    return errors


def _sampled_repair_region_errors(regions, errors, decimal_in):
    """Exact contract for same-image low-frequency sampling; old ops unchanged."""
    seen = set()

    def ellipse(value, subject, radii=True):
        names = {'x', 'y', 'radius_x_pixels', 'radius_y_pixels'} if radii else {'x', 'y'}
        if not isinstance(value, dict) or set(value) != names:
            errors.append(f'POSTPROCESS_SAMPLED_GEOMETRY_INVALID:{subject}')
            return
        for axis in ('x', 'y'):
            decimal_in(value[axis], '0', '1', f'{subject}.{axis}')
        if radii:
            for axis in ('radius_x_pixels', 'radius_y_pixels'):
                decimal_in(value[axis], '1', '512', f'{subject}.{axis}')

    for i, region in enumerate(regions):
        subject = f'regions[{i}]'
        required = {'id', 'target', 'donor', 'blur_radius_pixels', 'feather_fraction', 'strength', 'rgb_offset'}
        optional = {'detail_strength', 'exclusions'}
        if not isinstance(region, dict) or not required <= set(region) <= required | optional:
            errors.append(f'POSTPROCESS_REGION_KEYS_INVALID:{subject}')
            continue
        identifier = region['id']
        if not isinstance(identifier, str) or not IDENTIFIER_RE.fullmatch(identifier):
            errors.append(f'POSTPROCESS_INVALID_ID:{subject}')
        elif identifier in seen:
            errors.append(f'POSTPROCESS_DUPLICATE_ID:{identifier}')
        else:
            seen.add(identifier)
        ellipse(region['target'], f'{subject}.target')
        ellipse(region['donor'], f'{subject}.donor', False)
        for field, lower, upper in (
            ('blur_radius_pixels', '1', '64'), ('feather_fraction', '0.05', '1'),
            ('strength', '0', '1'), ('detail_strength', '0.85', '1'),
        ):
            if field in region:
                decimal_in(region[field], lower, upper, f'{subject}.{field}')
        offset = region['rgb_offset']
        if not isinstance(offset, dict) or set(offset) != {'r', 'g', 'b'}:
            errors.append(f'POSTPROCESS_SAMPLED_OFFSET_INVALID:{subject}')
        else:
            for channel in ('r', 'g', 'b'):
                decimal_in(offset[channel], '-0.05', '0.05', f'{subject}.rgb_offset.{channel}')
        exclusions = region.get('exclusions', [])
        if not isinstance(exclusions, list) or len(exclusions) > 16:
            errors.append(f'POSTPROCESS_SAMPLED_EXCLUSIONS_INVALID:{subject}')
        else:
            for j, exclusion in enumerate(exclusions):
                ellipse(exclusion, f'{subject}.exclusions[{j}]')
    return errors


def _same_source_restore_region_errors(regions, errors, decimal_in):
    required = {'id', 'polygon', 'exclusions', 'feather_pixels', 'strength', 'mode', 'band_radius_pixels', 'base', 'source'}
    seen = set()

    def polygon(points, subject):
        if not isinstance(points, list) or not 3 <= len(points) <= 64:
            errors.append(f'POSTPROCESS_POLYGON_INVALID:{subject}')
            return
        vertices = []
        for i, p in enumerate(points):
            if not isinstance(p, dict) or set(p) != {'x', 'y'}:
                errors.append(f'POSTPROCESS_POINT_INVALID:{subject}[{i}]')
                continue
            x = decimal_in(p['x'], '0', '1', f'{subject}[{i}].x')
            y = decimal_in(p['y'], '0', '1', f'{subject}[{i}].y')
            if x is not None and y is not None:
                vertices.append((x, y))
        if len(vertices) == len(points):
            if len(set(vertices)) != len(vertices):
                errors.append(f'POSTPROCESS_REPEATED_VERTEX:{subject}')
            area = abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(vertices,vertices[1:]+vertices[:1]))) / 2
            if not Decimal('0') < area <= Decimal('0.02'):
                errors.append(f'POSTPROCESS_AREA_OUT_OF_BOUNDS:{subject}')

    for i, region in enumerate(regions):
        subject = f'regions[{i}]'
        if not isinstance(region, dict) or set(region) != required:
            errors.append(f'POSTPROCESS_REGION_KEYS_INVALID:{subject}')
            continue
        identifier = region['id']
        if not isinstance(identifier, str) or not re.fullmatch(r'[a-z][a-z0-9_.-]{0,63}', identifier):
            errors.append(f'POSTPROCESS_INVALID_ID:{subject}')
        elif identifier in seen:
            errors.append(f'POSTPROCESS_DUPLICATE_ID:{identifier}')
        else:
            seen.add(identifier)
        polygon(region['polygon'], subject+'.polygon')
        exclusions = region['exclusions']
        if not isinstance(exclusions, list) or len(exclusions) > 8:
            errors.append(f'POSTPROCESS_RESTORE_EXCLUSIONS_INVALID:{subject}')
        else:
            for j, p in enumerate(exclusions):
                polygon(p, f'{subject}.exclusions[{j}]')
        decimal_in(region['feather_pixels'], '0', '128', subject+'.feather_pixels')
        decimal_in(region['strength'], '0', '1', subject+'.strength')
        decimal_in(region['band_radius_pixels'], '1', '64', subject+'.band_radius_pixels')
        if region['mode'] not in ('pixels', 'texture'):
            errors.append(f'POSTPROCESS_RESTORE_MODE_INVALID:{subject}')
        for label in ('base', 'source'):
            binding = region[label]
            if not isinstance(binding, dict) or set(binding) != {'manifest','manifest_sha256','master_sha256'}:
                errors.append(f'POSTPROCESS_RESTORE_BINDING_INVALID:{subject}.{label}')
                continue
            path = binding['manifest']
            if (not isinstance(path, str) or not path.startswith('output/') or not path.endswith('.manifest.json')
                    or any(part in ('','..','.') for part in path.split('/')) or '\\' in path):
                errors.append(f'POSTPROCESS_RESTORE_PATH_INVALID:{subject}.{label}')
            for field in ('manifest_sha256','master_sha256'):
                if not isinstance(binding[field], str) or not SHA256_RE.fullmatch(binding[field]):
                    errors.append(f'POSTPROCESS_RESTORE_HASH_INVALID:{subject}.{label}.{field}')
    return errors


def _tonal_brush_region_errors(regions, errors, decimal_in):
    required = {'id','polygon','exclusions','feather_pixels','gate_blur_radius_pixels','luminance_gate','controls'}
    seen = set()
    def check_polygon(points, subject):
        if not isinstance(points,list) or not 3 <= len(points) <= 64:
            errors.append(f'POSTPROCESS_POLYGON_INVALID:{subject}')
            return
        vertices = []
        for i,p in enumerate(points):
            if not isinstance(p,dict) or set(p) != {'x','y'}:
                errors.append(f'POSTPROCESS_POINT_INVALID:{subject}[{i}]')
                continue
            x=decimal_in(p['x'],'0','1',subject+f'[{i}].x')
            y=decimal_in(p['y'],'0','1',subject+f'[{i}].y')
            if x is not None and y is not None:vertices.append((x,y))
        if len(vertices)==len(points):
            if len(set(vertices))!=len(vertices):errors.append(f'POSTPROCESS_REPEATED_VERTEX:{subject}')
            area=abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(vertices,vertices[1:]+vertices[:1])))/2
            if not Decimal('0')<area<=Decimal('0.02'):errors.append(f'POSTPROCESS_AREA_OUT_OF_BOUNDS:{subject}')
    for i,region in enumerate(regions):
        subject=f'regions[{i}]'
        if not isinstance(region,dict) or set(region)!=required:
            errors.append(f'POSTPROCESS_REGION_KEYS_INVALID:{subject}')
            continue
        identifier=region['id']
        if not isinstance(identifier,str) or not IDENTIFIER_RE.fullmatch(identifier):
            errors.append(f'POSTPROCESS_INVALID_ID:{subject}')
        elif identifier in seen:errors.append(f'POSTPROCESS_DUPLICATE_ID:{identifier}')
        else:seen.add(identifier)
        check_polygon(region['polygon'],subject+'.polygon')
        if not isinstance(region['exclusions'],list) or len(region['exclusions'])>8:
            errors.append(f'POSTPROCESS_TONAL_EXCLUSIONS_INVALID:{subject}')
        else:
            for j,p in enumerate(region['exclusions']):check_polygon(p,f'{subject}.exclusions[{j}]')
        decimal_in(region['feather_pixels'],'0','128',subject+'.feather_pixels')
        decimal_in(region['gate_blur_radius_pixels'],'1','32',subject+'.gate_blur_radius_pixels')
        gate=region['luminance_gate'];gate_keys=('low','low_full','high_full','high')
        if not isinstance(gate,dict) or set(gate)!=set(gate_keys):errors.append(f'POSTPROCESS_TONAL_GATE_INVALID:{subject}')
        else:
            vals=[decimal_in(gate[k],'0','100',subject+'.luminance_gate.'+k) for k in gate_keys]
            if all(v is not None for v in vals) and not vals[0]<vals[1]<=vals[2]<vals[3]:errors.append(f'POSTPROCESS_TONAL_GATE_ORDER_INVALID:{subject}')
        controls=region['controls'];control_ids=set()
        if not isinstance(controls,list) or not 1<=len(controls)<=32:
            errors.append(f'POSTPROCESS_CONTROLS_INVALID:{subject}')
            continue
        for j,c in enumerate(controls):
            cs=f'{subject}.controls[{j}]'
            if not isinstance(c,dict) or set(c)!={'id','x','y','radius_pixels','delta_l'}:
                errors.append(f'POSTPROCESS_CONTROL_KEYS_INVALID:{cs}')
                continue
            cid=c['id']
            if not isinstance(cid,str) or not IDENTIFIER_RE.fullmatch(cid):errors.append(f'POSTPROCESS_INVALID_CONTROL_ID:{cs}')
            elif cid in control_ids:errors.append(f'POSTPROCESS_DUPLICATE_CONTROL_ID:{cid}')
            else:control_ids.add(cid)
            for k,lo,hi in [('x','0','1'),('y','0','1'),('radius_pixels','4','128'),('delta_l','-12','12')]:
                decimal_in(c[k],lo,hi,cs+'.'+k)
    return errors


def _spatial_light_region_errors(regions, errors, decimal_in):
    common = {'id', 'type', 'center', 'radius', 'rotation_degrees', 'exposure_ev'}
    seen = set()
    for index, region in enumerate(regions):
        subject = f'regions[{index}]'
        if (not isinstance(region, dict) or not isinstance(region.get('type'), str)
                or region['type'] not in {'ellipse', 'vignette'}):
            errors.append(f'POSTPROCESS_SPATIAL_TYPE_INVALID:{subject}')
            continue
        required = common | ({'inner_radius', 'outer_radius'} if region['type'] == 'vignette' else set())
        if not required <= set(region) <= required | {'luminance_gate'}:
            errors.append(f'POSTPROCESS_REGION_KEYS_INVALID:{subject}')
            continue
        identifier = region['id']
        if not isinstance(identifier, str) or not IDENTIFIER_RE.fullmatch(identifier):
            errors.append(f'POSTPROCESS_INVALID_ID:{subject}')
        elif identifier in seen:
            errors.append(f'POSTPROCESS_DUPLICATE_ID:{identifier}')
        else:
            seen.add(identifier)
        for key, names, lower, upper in (('center', ('x', 'y'), '0', '1'),
                                          ('radius', ('rx', 'ry'), '0.01', '2')):
            value = region[key]
            if not isinstance(value, dict) or set(value) != set(names):
                errors.append(f'POSTPROCESS_SPATIAL_PAIR_INVALID:{subject}.{key}')
            else:
                for name in names:
                    decimal_in(value[name], lower, upper, f'{subject}.{key}.{name}')
        decimal_in(region['rotation_degrees'], '-180', '180', subject + '.rotation_degrees')
        decimal_in(region['exposure_ev'], '-0.75', '0.75', subject + '.exposure_ev')
        if region['type'] == 'vignette':
            inner = decimal_in(region['inner_radius'], '0', '2', subject + '.inner_radius')
            outer = decimal_in(region['outer_radius'], '0.01', '3', subject + '.outer_radius')
            if inner is not None and outer is not None and not inner < outer:
                errors.append(f'POSTPROCESS_SPATIAL_RADII_ORDER_INVALID:{subject}')
            elif inner is not None and outer is not None and not float(inner) < float(outer):
                errors.append(f'POSTPROCESS_SPATIAL_RADII_FLOAT_COLLAPSE:{subject}')
        if 'luminance_gate' in region:
            gate = region['luminance_gate']
            keys = ('low', 'low_full', 'high_full', 'high')
            if not isinstance(gate, dict) or set(gate) != set(keys):
                errors.append(f'POSTPROCESS_SPATIAL_GATE_INVALID:{subject}')
            else:
                values = [decimal_in(gate[key], '0', '1', f'{subject}.luminance_gate.{key}') for key in keys]
                if all(value is not None for value in values):
                    if not values[0] < values[1] <= values[2] < values[3]:
                        errors.append(f'POSTPROCESS_SPATIAL_GATE_ORDER_INVALID:{subject}')
                    elif not float(values[0]) < float(values[1]) <= float(values[2]) < float(values[3]):
                        errors.append(f'POSTPROCESS_SPATIAL_GATE_FLOAT_COLLAPSE:{subject}')
    return errors


def _same_image_clone_region_errors(regions, errors, decimal_in):
    seen = set()
    for i, region in enumerate(regions):
        subject = f'regions[{i}]'
        if not isinstance(region, dict) or set(region) != {'id', 'polygon', 'donor_offset', 'feather_pixels'}:
            errors.append(f'POSTPROCESS_REGION_KEYS_INVALID:{subject}')
            continue
        identifier = region['id']
        if not isinstance(identifier, str) or not IDENTIFIER_RE.fullmatch(identifier):
            errors.append(f'POSTPROCESS_INVALID_ID:{subject}')
        elif identifier in seen:
            errors.append(f'POSTPROCESS_DUPLICATE_ID:{identifier}')
        else:
            seen.add(identifier)
        decimal_in(region['feather_pixels'], '0', '32', subject + '.feather_pixels')
        offset = region['donor_offset']
        if not isinstance(offset, dict) or set(offset) != {'x', 'y'}:
            errors.append(f'POSTPROCESS_CLONE_OFFSET_INVALID:{subject}')
        else:
            values = [decimal_in(offset[k], '-1', '1', subject + '.donor_offset.' + k) for k in ('x', 'y')]
            if all(value is not None for value in values) and not any(values):
                errors.append(f'POSTPROCESS_CLONE_ZERO_TRANSLATION:{subject}')
        points = region['polygon']
        if not isinstance(points, list) or not 3 <= len(points) <= 64:
            errors.append(f'POSTPROCESS_POLYGON_INVALID:{subject}')
            continue
        vertices = []
        for j, point in enumerate(points):
            if not isinstance(point, dict) or set(point) != {'x', 'y'}:
                errors.append(f'POSTPROCESS_POINT_INVALID:{subject}[{j}]')
                continue
            x = decimal_in(point['x'], '0', '1', f'{subject}.polygon[{j}].x')
            y = decimal_in(point['y'], '0', '1', f'{subject}.polygon[{j}].y')
            if x is not None and y is not None:
                vertices.append((x, y))
        if len(vertices) != len(points):
            continue
        if len(set(vertices)) != len(vertices):
            errors.append(f'POSTPROCESS_REPEATED_VERTEX:{subject}')
        with localcontext() as context:
            context.prec = 160
            area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(vertices, vertices[1:] + vertices[:1]))) / 2
            if not Decimal('0') < area <= Decimal('0.1'):
                errors.append(f'POSTPROCESS_AREA_OUT_OF_BOUNDS:{subject}')
            edges = list(zip(vertices, vertices[1:] + vertices[:1]))
            def cross(a, b, c):
                return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])
            for j, (a, b) in enumerate(edges):
                for k, (c, d) in enumerate(edges):
                    if k <= j + 1 or (j == 0 and k == len(edges) - 1):
                        continue
                    boxes_intersect = (max(min(a[0], b[0]), min(c[0], d[0])) <= min(max(a[0], b[0]), max(c[0], d[0])) and
                                       max(min(a[1], b[1]), min(c[1], d[1])) <= min(max(a[1], b[1]), max(c[1], d[1])))
                    if boxes_intersect and cross(a, b, c)*cross(a, b, d) <= 0 and cross(c, d, a)*cross(c, d, b) <= 0:
                        errors.append(f'POSTPROCESS_SELF_INTERSECTION:{subject}')
    return errors


def _postprocess_recipe_errors(recipe: Any) -> list[str]:
    """Validate the exact bounded local algorithm contract without reading images."""

    if not isinstance(recipe, dict):
        return ["POSTPROCESS_NOT_OBJECT"]
    errors: list[str] = []
    expected_keys = {"schema_version", "coordinate_space", "operation_id", "regions", "recipe_sha256"}
    if recipe.get('operation_id') == LOCAL_SAME_IMAGE_CLONE_OPERATION_ID:
        expected_keys.add('purpose')
        if recipe.get('purpose') != 'shadow_cleanup':
            errors.append('POSTPROCESS_CLONE_PURPOSE_INVALID')
    if set(recipe) != expected_keys:
        errors.append("POSTPROCESS_KEYS_INVALID")
    operation_id = recipe.get("operation_id")
    expected_version = LOCAL_RECIPE_SCHEMAS.get(operation_id) if isinstance(operation_id, str) else None
    if expected_version is None:
        errors.append("POSTPROCESS_OPERATION_UNSUPPORTED")
    if expected_version is None or recipe.get("schema_version") != expected_version:
        errors.append("POSTPROCESS_VERSION_MISMATCH")
    if recipe.get("coordinate_space") != "normalized_upright":
        errors.append("POSTPROCESS_COORDINATE_SPACE_MISMATCH")
    claimed_hash = recipe.get("recipe_sha256")
    try:
        hash_matches = (
            isinstance(claimed_hash, str)
            and SHA256_RE.fullmatch(claimed_hash) is not None
            and postprocess_recipe_sha256(recipe) == claimed_hash
        )
    except (TypeError, ValueError):
        hash_matches = False
    if not hash_matches:
        errors.append("POSTPROCESS_HASH_MISMATCH")
    regions = recipe.get("regions")
    max_regions = 16 if operation_id == LOCAL_SAMPLED_REPAIR_OPERATION_ID else 4
    if not isinstance(regions, list) or not 1 <= len(regions) <= max_regions:
        errors.append("POSTPROCESS_REGIONS_INVALID")
        return errors

    def decimal_in(value: Any, lower: str, upper: str, subject: str) -> Decimal | None:
        if not isinstance(value, str) or len(value) > 64 or not DECIMAL_STRING_RE.fullmatch(value):
            errors.append(f"POSTPROCESS_INVALID_DECIMAL:{subject}")
            return None
        parsed = Decimal(value)
        if not Decimal(lower) <= parsed <= Decimal(upper):
            errors.append(f"POSTPROCESS_RANGE_MISMATCH:{subject}")
            return None
        return parsed

    if operation_id == LOCAL_SUN_GLOW_OPERATION_ID:
        return _sun_glow_region_errors(regions, errors, decimal_in)
    if operation_id == LOCAL_SAMPLED_REPAIR_OPERATION_ID:
        return _sampled_repair_region_errors(regions, errors, decimal_in)
    if operation_id == LOCAL_SAME_SOURCE_RESTORE_OPERATION_ID:
        return _same_source_restore_region_errors(regions, errors, decimal_in)
    if operation_id == LOCAL_TONAL_BRUSH_OPERATION_ID:
        return _tonal_brush_region_errors(regions, errors, decimal_in)
    if operation_id == LOCAL_SPATIAL_LIGHT_OPERATION_ID:
        return _spatial_light_region_errors(regions, errors, decimal_in)
    if operation_id == LOCAL_SAME_IMAGE_CLONE_OPERATION_ID:
        return _same_image_clone_region_errors(regions, errors, decimal_in)

    def crosses(a, b, c, d) -> bool:
        def orientation(p, q, r):
            return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

        def on_segment(p, q, r):
            return min(p[0], r[0]) <= q[0] <= max(p[0], r[0]) and min(p[1], r[1]) <= q[1] <= max(p[1], r[1])

        abc, abd = orientation(a, b, c), orientation(a, b, d)
        cda, cdb = orientation(c, d, a), orientation(c, d, b)
        if (abc > 0) != (abd > 0) and (cda > 0) != (cdb > 0) and all((abc, abd, cda, cdb)):
            return True
        return (
            (abc == 0 and on_segment(a, c, b)) or (abd == 0 and on_segment(a, d, b))
            or (cda == 0 and on_segment(c, a, d)) or (cdb == 0 and on_segment(c, b, d))
        )

    seen_ids: set[str] = set()
    seen_control_ids: set[str] = set()
    skin_field = operation_id == LOCAL_SKIN_OPERATION_ID
    skin_texture = operation_id == LOCAL_TEXTURE_OPERATION_ID
    for index, region in enumerate(regions):
        subject = f"regions[{index}]"
        required_region_keys = {"id", "polygon", "feather_pixels", "radius_pixels", "sigma_color", "strength"} if skin_texture else {"id", "polygon", "feather_pixels", "controls"} if skin_field else {
            "id", "polygon", "blur_radius_pixels", "feather_pixels", "strength", "max_gain_ev", "iterations"
        }
        optional_region_keys = set() if skin_field or skin_texture else {"chroma_balance"}
        if not isinstance(region, dict) or not (
            required_region_keys <= set(region) <= required_region_keys | optional_region_keys
        ):
            errors.append(f"POSTPROCESS_REGION_KEYS_INVALID:{subject}")
            continue
        region_id = region["id"]
        if not isinstance(region_id, str) or not IDENTIFIER_RE.fullmatch(region_id):
            errors.append(f"POSTPROCESS_INVALID_ID:{subject}")
        elif region_id in seen_ids:
            errors.append(f"POSTPROCESS_DUPLICATE_ID:{region_id}")
        else:
            seen_ids.add(region_id)
        decimal_in(region["feather_pixels"], "0", "32", f"{subject}.feather_pixels")
        if skin_texture:
            radius = region["radius_pixels"]
            if type(radius) is not int or not 1 <= radius <= 8:
                errors.append(f"POSTPROCESS_RADIUS_INVALID:{subject}")
            decimal_in(region["sigma_color"], "0.005", "0.15", f"{subject}.sigma_color")
            decimal_in(region["strength"], "0", "1", f"{subject}.strength")
        elif skin_field:
            controls = region["controls"]
            if not isinstance(controls, list) or not 1 <= len(controls) <= 32:
                errors.append(f"POSTPROCESS_CONTROLS_INVALID:{subject}")
            else:
                for control_index, control in enumerate(controls):
                    control_subject = f"{subject}.controls[{control_index}]"
                    if not isinstance(control, dict) or set(control) != {
                        "id", "x", "y", "radius_pixels", "delta_l", "delta_a", "delta_b"
                    }:
                        errors.append(f"POSTPROCESS_CONTROL_KEYS_INVALID:{control_subject}")
                        continue
                    control_id = control["id"]
                    if not isinstance(control_id, str) or not IDENTIFIER_RE.fullmatch(control_id):
                        errors.append(f"POSTPROCESS_INVALID_CONTROL_ID:{control_subject}")
                    elif control_id in seen_control_ids:
                        errors.append(f"POSTPROCESS_DUPLICATE_CONTROL_ID:{control_id}")
                    else:
                        seen_control_ids.add(control_id)
                    for name, lower, upper in (
                        ("x", "0", "1"), ("y", "0", "1"), ("radius_pixels", "4", "128"),
                        ("delta_l", "-12", "12"), ("delta_a", "-8", "8"), ("delta_b", "-8", "8"),
                    ):
                        decimal_in(control[name], lower, upper, f"{control_subject}.{name}")
        else:
            for name, lower, upper in (
                ("blur_radius_pixels", "1", "64"), ("strength", "0", "1"), ("max_gain_ev", "0", "1"),
            ):
                decimal_in(region[name], lower, upper, f"{subject}.{name}")
            if "chroma_balance" in region:
                chroma = region["chroma_balance"]
                chroma_fields = {
                    "target_red_green_ratio", "target_blue_green_ratio", "strength", "max_log_ratio_shift"
                }
                if not isinstance(chroma, dict) or set(chroma) != chroma_fields:
                    errors.append(f"POSTPROCESS_CHROMA_KEYS_INVALID:{subject}.chroma_balance")
                else:
                    for name, lower, upper in (
                        ("target_red_green_ratio", "0.5", "2"),
                        ("target_blue_green_ratio", "0.5", "2"),
                        ("strength", "0", "1"), ("max_log_ratio_shift", "0", "0.35"),
                    ):
                        decimal_in(chroma[name], lower, upper, f"{subject}.chroma_balance.{name}")
            iterations = region["iterations"]
            if type(iterations) is not int or not 1 <= iterations <= 4000:
                errors.append(f"POSTPROCESS_ITERATIONS_INVALID:{subject}")
        polygon = region["polygon"]
        if not isinstance(polygon, list) or not 3 <= len(polygon) <= 64:
            errors.append(f"POSTPROCESS_POLYGON_INVALID:{subject}")
            continue
        points = []
        for point_index, point in enumerate(polygon):
            point_subject = f"{subject}.polygon[{point_index}]"
            if not isinstance(point, dict) or set(point) != {"x", "y"}:
                errors.append(f"POSTPROCESS_POINT_INVALID:{point_subject}")
                continue
            x = decimal_in(point["x"], "0", "1", f"{point_subject}.x")
            y = decimal_in(point["y"], "0", "1", f"{point_subject}.y")
            if x is not None and y is not None:
                points.append((x, y))
        if len(points) != len(polygon):
            continue
        if len(set(points)) != len(points):
            errors.append(f"POSTPROCESS_REPEATED_VERTEX:{subject}")
        # Preserve exact boundary decisions for all accepted 64-character decimals.
        with localcontext() as context:
            context.prec = 160
            twice_area = abs(sum(
                a[0] * b[1] - b[0] * a[1]
                for a, b in zip(points, points[1:] + points[:1])
            ))
            if not Decimal("0") < twice_area < Decimal("0.04"):
                errors.append(f"POSTPROCESS_AREA_OUT_OF_BOUNDS:{subject}")
            edges = list(zip(points, points[1:] + points[:1]))
            if any(
                crosses(a, b, c, d)
                for i, (a, b) in enumerate(edges)
                for j, (c, d) in enumerate(edges)
                if j > i + 1 and not (i == 0 and j == len(edges) - 1)
            ):
                errors.append(f"POSTPROCESS_SELF_INTERSECTION:{subject}")
    return errors


def validate_postprocess_recipe(recipe: dict[str, Any]) -> None:
    """Dispatch an approved local recipe, checking bounded geometry and exact hash."""

    errors = _postprocess_recipe_errors(recipe)
    if errors:
        raise OperationRegistryError("invalid postprocess recipe: " + "; ".join(errors))


def semantic_card_errors(card: dict[str, Any], registry: dict[str, Any] | None = None) -> list[str]:
    """Return stable semantic admission errors for a schema-valid technique card."""

    registry = registry or load_operation_registry()
    by_field = operations_by_field(registry)
    by_id = operations_by_id(registry)
    status = card.get("status", "draft")
    errors: list[str] = []
    seen_parameter_fields: set[str] = set()

    for rule in card.get("parameter_rules", []):
        field = rule["field"]
        if field in seen_parameter_fields:
            errors.append(f"DUPLICATE_PARAMETER_FIELD:{field}")
        seen_parameter_fields.add(field)
        operation = by_field.get(field)
        if operation is None:
            errors.append(f"UNKNOWN_FIELD:{field}")
            continue
        errors.extend(_admission_errors(operation, status, field))

        value_spec = rule["value_spec"]
        if value_spec["kind"] == "formula" and status in {"candidate", "frozen"}:
            errors.append(f"FORMULA_NOT_EXECUTABLE:{field}:status={status}")
        actual_unit = _rule_unit(value_spec)
        expected_unit = operation["native_unit"]
        if actual_unit != expected_unit:
            errors.append(f"UNIT_MISMATCH:{field}:expected={expected_unit}:actual={actual_unit}")

        expected_type = operation["value_type"]
        if value_spec["kind"] == "formula":
            actual_type = "scalar"
        else:
            scalar_type = value_spec["value"]["type"]
            if scalar_type == "enum":
                actual_type = "enum"
            elif scalar_type == "curve":
                actual_type = "curve"
            else:
                actual_type = "scalar"
        if actual_type != expected_type:
            errors.append(f"VALUE_TYPE_MISMATCH:{field}:expected={expected_type}:actual={actual_type}")
        elif expected_type == "enum" and value_spec["kind"] == "absolute":
            scalar = value_spec["value"]
            domain = enum_domain_for_operation(operation, registry)
            if scalar.get("domain_ref") != operation["enum_domain_ref"]:
                errors.append(f"ENUM_DOMAIN_MISMATCH:{field}")
            elif domain is None or scalar["value"] not in domain["native_values"]:
                errors.append(f"UNKNOWN_ENUM_TOKEN:{field}:{scalar['value']}")
        elif expected_type == "curve" and value_spec["kind"] == "absolute":
            if rule["allowed_range"] is not None:
                errors.append(f"CURVE_ALLOWED_RANGE_MUST_BE_NULL:{field}")
            try:
                native_parameter_value(field, value_spec["value"], registry)
            except OperationRegistryError as exc:
                errors.append(f"INVALID_CURVE:{field}:{exc}")

        native_range = operation["native_range"]
        allowed_range = rule["allowed_range"]
        if native_range is not None and allowed_range is not None:
            allowed_lower = Decimal(allowed_range["lower"])
            allowed_upper = Decimal(allowed_range["upper"])
            if allowed_lower > allowed_upper:
                errors.append(f"ALLOWED_RANGE_REVERSED:{field}")
            if not _inside(allowed_lower, native_range) or not _inside(allowed_upper, native_range):
                errors.append(f"ALLOWED_RANGE_OUTSIDE_NATIVE:{field}")
        if native_range is not None and value_spec["kind"] == "absolute":
            scalar = value_spec["value"]
            if scalar["type"] in {"decimal", "integer"}:
                value = Decimal(scalar["value"])
                if not _inside(value, native_range):
                    errors.append(f"NATIVE_RANGE_MISMATCH:{field}:value={scalar['value']}")
                if allowed_range is not None and not _inside(value, allowed_range):
                    errors.append(f"CARD_RANGE_MISMATCH:{field}:value={scalar['value']}")

    crop_fields = {'hascrop', 'cropleft', 'croptop', 'cropright', 'cropbottom', 'cropangle'}
    present_crop = seen_parameter_fields & crop_fields
    if present_crop:
        if present_crop != crop_fields:
            errors.append('NATIVE_CROP_REQUIRES_COMPLETE_GROUP')
        else:
            crop_rules = {r['field']: r['value_spec'] for r in card['parameter_rules'] if r['field'] in crop_fields}
            try:
                if any(spec['kind'] != 'absolute' for spec in crop_rules.values()):
                    raise ValueError('absolute geometry required')
                crop = {field: native_parameter_value(field, spec['value'], registry) for field, spec in crop_rules.items()}
                values = {field: Decimal(value) for field, value in crop.items() if field != 'hascrop'}
                if crop['hascrop'] != 'True' or not all(x.is_finite() for x in values.values()) or not (
                    0 <= values['cropleft'] < values['cropright'] <= 1 and
                    0 <= values['croptop'] < values['cropbottom'] <= 1 and -3 <= values['cropangle'] <= 3):
                    raise ValueError('invalid active crop')
            except (ValueError, KeyError, TypeError, ArithmeticError):
                errors.append('NATIVE_CROP_INVALID_GROUP')

    mask_recipe = card.get("mask_recipe")
    if mask_recipe is not None:
        errors.extend(_mask_graph_errors(mask_recipe))
        for kind in sorted({mask["type"] for group in mask_recipe["groups"] for mask in group["masks"]}):
            operation_id = MASK_OPERATION_IDS.get(kind)
            if operation_id is None:
                errors.append(f"MASK_UNSUPPORTED_SELECTOR:{kind}")
            else:
                errors.extend(_admission_errors(by_id[operation_id], status, operation_id))

    postprocess_recipe = card.get("postprocess_recipe")
    if postprocess_recipe is not None:
        errors.extend(_postprocess_recipe_errors(postprocess_recipe))
        operation_id = postprocess_recipe.get("operation_id") if isinstance(postprocess_recipe, dict) else None
        operation = by_id.get(operation_id) if isinstance(operation_id, str) else None
        if operation is None:
            errors.append(f"UNKNOWN_POSTPROCESS_OPERATION:{operation_id}")
        else:
            errors.extend(_admission_errors(operation, status, operation_id))
        if operation_id in card.get("forbidden_operations", []):
            errors.append(f"POSTPROCESS_OPERATION_FORBIDDEN_BY_CARD:{operation_id}")

    for operation_id in card.get("forbidden_operations", []):
        if operation_id not in by_id:
            errors.append(f"UNKNOWN_FORBIDDEN_OPERATION:{operation_id}")
    return errors
