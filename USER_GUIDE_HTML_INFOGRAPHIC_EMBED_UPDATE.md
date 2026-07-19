# User Guide HTML Infographic Embed Update

The 18-page annotated ProjectReady AI infographic is now part of the `/user-guide` page as a responsive HTML viewer rather than a browser PDF object.

## Included behaviour

- full-width 16:9 annotated pages rendered as optimized WebP assets;
- module tabs for Getting Started, Topic Ideas, Thesis Workspace, Chapter Strengthener and Final Review;
- Previous and Next controls;
- page counter and full-size image link;
- scrollable page thumbnails;
- keyboard navigation with Left, Right, Home and End;
- accessible page titles, descriptions and image alternatives;
- original PDF retained for printing and offline use.

## Updated files

- `app/static/user_guide.html`
- `app/static/user_guide.css`
- `app/static/user_guide.js`
- `app/static/guides/annotated-html/pages/page-01.webp` through `page-18.webp`
- `app/static/guides/annotated-html/thumbs/page-01.webp` through `page-18.webp`
- `tests/test_user_guide_integration.py`
