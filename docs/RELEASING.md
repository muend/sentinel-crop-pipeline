# Releasing

Version lives in three places; keep them in sync:
`pyproject.toml` (`version`), `src/sentinel_crop_pipeline/__init__.py`
(`__version__`), `CITATION.cff` (`version` + `date-released`).

## One-time setup

### PyPI (trusted publishing, no tokens)

1. Create a PyPI account at https://pypi.org (enable 2FA).
2. PyPI -> Account settings -> Publishing -> "Add a new pending publisher":
   - PyPI project name: `sentinel-crop-pipeline`
   - Owner: `muend`, Repository: `sentinel-crop-pipeline`
   - Workflow name: `release.yml`
   - Environment name: `pypi`
3. GitHub repo -> Settings -> Environments -> New environment named `pypi`
   (no secrets needed; optionally require your own review).

After the first successful publish the "pending" publisher becomes permanent.

### Zenodo (DOI per release)

1. Log in at https://zenodo.org with your GitHub account.
2. https://zenodo.org/account/settings/github/ -> flip the toggle for
   `muend/sentinel-crop-pipeline` to ON. Do this BEFORE publishing the
   release you want archived — Zenodo only archives releases made after the
   toggle.
3. Metadata is read from `.zenodo.json`. After the first archived release,
   copy the "all versions" DOI badge from the Zenodo record into README.md
   and the `doi` field into CITATION.cff.

## Per release

```bash
# 1. bump versions (three files above), update README/HANDOFF if needed
python -m pytest                      # must be green
git add -A && git commit -m "Release vX.Y.Z"
git push

# 2. tag
git tag vX.Y.Z
git push origin vX.Y.Z
```

3. GitHub -> Releases -> "Draft a new release" -> choose tag `vX.Y.Z`,
   title like `vX.Y.Z — <one-line summary>`, paste changelog, publish.
   Publishing triggers `release.yml` (PyPI) and the Zenodo archive.
4. Check: Actions tab shows the release job green; the package appears at
   https://pypi.org/project/sentinel-crop-pipeline/ and installs with
   `pip install sentinel-crop-pipeline` or `uv pip install sentinel-crop-pipeline`;
   Zenodo shows a new version DOI.
