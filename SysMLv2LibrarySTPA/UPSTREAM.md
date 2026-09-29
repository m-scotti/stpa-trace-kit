# Provenance of this folder

Everything in this folder is DLR's, unmodified.

- Upstream: https://github.com/DLR-FT/SysMLv2LibrarySTPA
- Commit: `cde7d6aadb0ecb839cf93c7519974180ac8f3398` (2026-07-17, "Updated jupyter to newest version")
- License: MIT or Apache 2.0, at your choice (`LICENSE-MIT`, `LICENSE-APACHE`). Copyright DLR.

Copied from that commit: `Library/LibrarySTPA.sysml`, `Library/ExampleSTPA.sysml`, `README.md`,
both license files. Left out: `Library/CameoViewsSTPA.sysml` (about 285 Syside errors, not
imported by the example model), `Jupyter/`, `Images/`.

There is no local patch. Before packaging, `git status` and `git diff` in the source checkout
showed no changes, no local commits, and `origin/main` at the commit above.

To check these files against upstream:

    git clone https://github.com/DLR-FT/SysMLv2LibrarySTPA upstream
    git -C upstream checkout cde7d6aadb0ecb839cf93c7519974180ac8f3398
    diff upstream/Library/LibrarySTPA.sysml Library/LibrarySTPA.sysml
    diff upstream/Library/ExampleSTPA.sysml Library/ExampleSTPA.sysml

If you change the library at work, keep this copy unmodified and record your changes as a
patch against this commit (`git diff > local-changes.patch` in a checkout of it).
