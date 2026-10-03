# Release candidate status

Version: 0.1.0-alpha.1. Experimental public source package under the MIT license.

- Core: Python 3.11+ standard library; optional Pillow 12.3.0 for safe previews.
- Runtime: macOS, separately installed Photoshop and Camera Raw.
- Independent-folder installation, source guards, plan compiler and attempt budget
  are tested with non-photographic inputs. Private runtime history is not bundled.
- A real local Adobe test used an original synthetic DNG, neutral and +0.5 exposure
  variants, full 16-bit TIFF/JPEG exports and same-machine replay. Source integrity,
  repeat pixels, changed pixels and increased brightness all passed on Python 3.13.5,
  Apple Silicon, Photoshop 27.10.0, Camera Raw 18.6.
- The first smaller synthetic fixture was rejected by Adobe; the generator was
  corrected to a larger full-resolution-tagged DNG. This was a fixture failure,
  not a claim of camera compatibility.
- Independent forward testing found a symlink write escape in the wrapper's ingest
  paths. Path checks and a regression were added before packaging.
- True second-computer installation, all real camera formats, cross-version profile
  parity and artistic quality are not verified. The repository's Actions page is
  the source of current CI results. No hosted Photoshop test is claimed.

The owner approved the MIT license and public publication. No private photographs,
photo inventories, user preferences or chat history belong in this package.
The public GitHub account identifies the publisher; commits use its GitHub noreply
address, not a private email address. The original research knowledge library is
excluded; see [knowledge scope](KNOWLEDGE-SCOPE.md).

Before each publication, rerun tests, the exact allowlist check and clean archive
extraction. Check the actual Git index and commit identity separately: this text-only
archive does not include a Git history or claim that an unrelated repository is clean.
