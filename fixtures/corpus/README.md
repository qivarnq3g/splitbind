# SplitBind synthetic acceptance corpus v1

This corpus is generated locally from deterministic vector drawing, gradients, and seeded pseudorandom grayscale pixels. It contains no source document, third-party photograph, recipient data, or other personal data. In `negative_external`, “external” means outside the SplitBind issuance set; those images are still synthetic.

Every artifact is released under `CC0-1.0`. The manifest records the generator version, seed, page count, dimensions, SHA-256 checksum, and license for every entry. No individual fixture may exceed 2,000,000 bytes.

Reproduce the checked-in corpus from the repository root:

```powershell
python research/python/scripts/generate_corpus.py --seed 20260827 --output fixtures/corpus/generated
```

The corpus includes three one-page PDFs, two multi-page PDFs, three clean raster images, ten independently seeded unwatermarked negative images, and one image with a normalized tamper ground-truth rectangle. PDF pages combine vector text, grayscale shapes, procedural raster imagery, whitespace, and mixed contrast.
