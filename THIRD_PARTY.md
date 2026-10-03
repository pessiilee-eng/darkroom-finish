# Dependencies and provenance

Core execution uses Python's standard library. Photoshop and Camera Raw are
separate Adobe products installed and licensed by the user; neither is bundled.

The optional preview helper uses Pillow 12.3.0, installed from PyPI. Its license
and contributors remain with the upstream package:
[Pillow license](https://github.com/python-pillow/Pillow/blob/main/LICENSE).
This archive does not vendor Pillow or Adobe software.

The fixture generator creates original programmatic color ramps. There are no
downloaded photographs, camera RAW samples, photographer presets, course assets
or image-generation model assets in this package.

The compiler, schema interpreter, geometry and source-protection code are adapted
from the author's local darkroom project. Private evidence has been removed;
registry entries do not inherit historical probe or review approval. Photography
guidance is expressed as general decision criteria, not claimed photographer
recipes. Public Adobe documentation links describe platform capabilities only.
