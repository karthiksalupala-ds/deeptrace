# DeepTrace synthetic reference images

`hikvision_reference.img` and `dahua_reference.img` are deterministic-format,
spec-accurate synthetic reference images for exercising the DeepTrace parsers.
Each contains 200 generated frame candidates, including 10 deliberately corrupted
candidates and 20 inserted fragmented/unallocated-space gaps.  They are **not**
images acquired from a seized DVR/NVR drive and must not be presented as such.

Their adjacent `.meta.json` files record the expected recovery counts.  Regenerate
them from the repository root with:

```powershell
.\.venv\Scripts\python.exe -m engine.synthetic_image_gen --manufacturer hikvision --out sample_data\hikvision_reference.img --frames 200 --corruption_rate 0.05
.\.venv\Scripts\python.exe -m engine.synthetic_image_gen --manufacturer dahua --out sample_data\dahua_reference.img --frames 200 --corruption_rate 0.05
```

The generator's default fragmentation mode is enabled by omission of
`--no-fragmentation`; this produces the 20 gaps documented above.
