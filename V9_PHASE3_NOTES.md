# Vasuki AI V9 Phase 3

Scope: roadmap items 14-22.

## Implemented

14. Image presets: Auto, Photo, Cinematic, Product, Poster, Logo, Anime, 3D.
15. Aspect ratios: 1:1, 4:5, 16:9, 9:16, 4:3. Data-URL generations are center-fitted to exact output dimensions.
16. Variations: 2-4 variations with composition variation hints and capped concurrency.
17. Image edit UI: `/images` is upgraded into Image Studio and uses the existing safe vision edit providers.
18. Upscale/enhancement: local Pillow LANCZOS + sharpening/contrast, up to 4x and 4096 px long edge.
19. OCR V2: image OCR through multimodal vision; PDFs use native extraction first and vision OCR fallback when no text is embedded.
20. Structured document extraction: PDF pages, DOCX headings/tables, TXT/MD line sections, image OCR blocks.
21. Document citations: source IDs include native PDF page, DOCX section, or TXT line location.
22. Document compare: deterministic similarity/added/removed samples plus AI comparison with citations.

## Important boundaries

- Local enhance/upscale is high-quality resampling; it is not generative super-resolution.
- Native PDFs receive reliable page citations from pypdf extraction.
- Scanned PDF vision fallback cannot guarantee page boundaries; the API returns a warning.
- DOCX does not expose reliable rendered page numbers without a layout engine, so citations are heading/section based.
- TXT/MD citations are line-section based.
- Image provider aspect control is guaranteed when a provider returns a data URL because V9 post-processes the image. External URL-only provider results may only receive prompt-level aspect guidance.
- Variations are generation variations, not latent-seed locking across different providers.
