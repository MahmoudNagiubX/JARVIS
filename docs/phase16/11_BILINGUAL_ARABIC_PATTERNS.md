# Phase 16: Bilingual Arabic & Egyptian Technical Phrase Patterns

## 1. Supported Extraction Phrases

JARVIS natively recognizes Egyptian Arabic, Modern Standard Arabic, and mixed Franco-Arabic technical phrasing:

| Phrase Category | Example Input | Extracted Category & Structured Data |
|---|---|---|
| Project Technology | `افتكر إن المشروع ده بيستخدم PostgreSQL للـbackend` | category=`project`, structured_data=`{"key": "project_phoenix_tech", "technology": "PostgreSQL"}` |
| Project Technology | `مشروع فينيكس بيستخدم Fastify` | category=`project`, structured_data=`{"key": "project_phoenix_tech", "technology": "Fastify"}` |
| Preferred Editor | `الـeditor المفضل هو PyCharm` | category=`preference`, structured_data=`{"key": "preferred_editor", "value": "PyCharm"}` |
| Preferred Editor | `محرر النصوص المفضل هو VS Code` | category=`preference`, structured_data=`{"key": "preferred_editor", "value": "VS Code"}` |
| Preferred Name | `اسمي هو محمود` / `ناديلي محمود` | category=`profile`, structured_data=`{"key": "preferred_name", "value": "محمود"}` |
| Goal | `الهدف بتاعي أخلص الـdocumentation الجمعة` | category=`goal`, structured_data=`{"key": "active_goal"}` |
| Goal | `هدفي هو شحن Phase 16 بنجاح` | category=`goal`, structured_data=`{"key": "active_goal"}` |
| Task & Deadline | `فكرني قبل الـdeadline بيوم` | category=`task`, structured_data=`{"key": "project_deadline"}` |

## 2. Arabic Search Normalization

The `normalize_text` pipeline handles Arabic orthographic variations:
- Diacritics (tashkeel): Strips `[\u064b-\u0652\u0670\u0640]`.
- Alef normalization: Maps `أ`, `إ`, `آ`, `ٱ` to `ا`.
- Teh Marbuta: Maps `ة\b` to `ه`.
- Alef Maksura / Yaa: Maps `ى\b` to `ي`.

This ensures queries searching for `إفتكر`, `المشروع`, or `بوستجريس` match both Arabic and mixed Latin records accurately.
