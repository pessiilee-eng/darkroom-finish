# Operation contract

<a id="implementation"></a>
## Implementation

This alpha contains an Adobe Camera Raw XMP compiler, not a Photoshop UI agent.
The registry specifies each field, native unit, range, enum domain and transport.
`schema_representable` and `executor_write` mean the compiler can validate and
serialize the operation; they do not establish visual quality or native readback.
The public registry does not inherit private fixture, replay or review evidence.
Each render still checks source integrity and repeat TIFF pixel equality.

The XMP compiler supports global tonal/color fields, ordered RGB point curves,
hand-authored brush/linear/radial/luminance mask graphs, and bounded native crop
geometry. See the registry for exact admission; do not write arbitrary XMP.
Native local Exposure2012 is restricted to [-1, 1]; do not treat it as global EV.
Radial nonzero local exposure is not part of the supported public workflow.
Native crop supports TIFF-family RAW orientation 1, 6, 8 and ±3 degrees only;
rotated-image masks support brushes only. Unsupported metadata must stop.

The alpha does not ship local raster retouching, generative tools, layer graphs,
face reshaping, automatic library selection, third-party review services or cloud
uploads. Local raster registry entries remain unavailable, not silently replaced.
Input RAW profile and Adobe persistent defaults are not fully captured. Record
Adobe/Camera Raw versions, compare an explicit baseline and inspect the image.
Do not promise cross-version or cross-machine identical rendering.

Primary documentation:

- [Adobe Camera Raw namespace](https://developer.adobe.com/xmp/docs/xmp-namespaces/crs/)
- [Color and tonal adjustments](https://helpx.adobe.com/camera-raw/using/make-color-tonal-adjustments-camera.html)
- [Masking in Camera Raw](https://helpx.adobe.com/camera-raw/using/masking.html)

These links document Adobe features. They do not assert that every feature has
been independently tested by this project.
