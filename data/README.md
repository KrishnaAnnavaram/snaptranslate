# data/

Git ignores everything in this folder except this file. Do not commit photos, test sets or exports.

## Bundled synthetic data (in `src/snaptranslate/data/`)

| File | Contents | Licence |
|---|---|---|
| `testset.jsonl` | 36 author-written travel sentences (12 each for German, French and Spanish) with an English reference | CC0-1.0 |
| `glossary.json` | Author-written travel glossary (de, fr, es, it to English) for the offline backend | CC0-1.0 |
| `langid_samples.json` | 10 author-written training sentences for each of 9 Latin-script languages | CC0-1.0 |

The glossary and the test set have the same author. Scores of the glossary backend on this test set are
optimistic. They show that the benchmark works. They do not show real translation quality.

## A real parallel test set: FLORES-200

- Source: FLORES-200 evaluation benchmark, <https://github.com/facebookresearch/flores>
- Licence: CC BY-SA 4.0
- Download the `devtest` files for each language that you need, for example `deu_Latn.devtest`,
  `fra_Latn.devtest`, `spa_Latn.devtest` and `eng_Latn.devtest`. The files are line-aligned.
- Change them into one JSONL file with one object for each line:

```json
{"id": "flores-de-0001", "src_lang": "de", "tgt_lang": "en", "src": "<German line>", "ref": "<English line>"}
```

- `src_lang` and `tgt_lang` accept any common code (`de`, `deu_Latn`, `German`).
- Save the file as `data/flores_de_en.jsonl` and run
  `snaptranslate benchmark --testset data/flores_de_en.jsonl --backends marian,nllb`.

WMT news test sets (<https://www.statmt.org/>) work the same way. Read the terms of each set.

## Photos

Use your own photos only. Signs and menus can show faces or private data. Do not commit photos.
