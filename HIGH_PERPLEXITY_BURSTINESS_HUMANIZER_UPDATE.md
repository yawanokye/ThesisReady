# High Perplexity and Burstiness Humanizer Update

The scholarly humanizer now defaults to high controlled perplexity and high controlled burstiness.

## Meaning of the settings

- High perplexity means richer context-sensitive lexical and syntactic variation. It does not mean obscure vocabulary, random synonyms or changes to technical terms.
- High burstiness means purposeful variation across concise, medium and longer synthesis sentences, together with varied paragraph length and argumentative movement.

## Protection rules

The humanizer still preserves citations, references, numbers, years, URLs, headings, objectives, research questions, hypotheses, equations, tables and red action items. Candidate revisions that breach the preservation gate are rejected.

## Default configuration

```env
PROJECTREADY_HUMANIZER_MODE=balanced
PROJECTREADY_HUMANIZER_PERPLEXITY_LEVEL=high
PROJECTREADY_HUMANIZER_BURSTINESS_LEVEL=high
PROJECTREADY_HUMANIZER_MODEL_THRESHOLD=97
PROJECTREADY_HUMANIZER_BATCH_WORDS=1800
PROJECTREADY_HUMANIZER_MAX_BATCHES_BALANCED=6
PROJECTREADY_HUMANIZER_MAX_BATCHES_DEEP=16
PROJECTREADY_HUMANIZER_MAX_WORD_CHANGE_RATIO=0.06
```

Balanced mode now also triggers a protected model pass when lexical diversity or sentence and paragraph rhythm fall below the high-variation targets, even where the earlier general naturalness score was acceptable.
