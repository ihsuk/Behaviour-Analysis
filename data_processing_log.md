# Data Processing & Transformation Log
**Author**: Khushi Pandey

This document details the database schema, data preparation steps, data cleaning assumptions, and SQL transformations applied to clean and aggregate the exam interaction logs.

---

## 1. Database Schema & Data Profile

The telemetry logs were restored to a PostgreSQL 18 database named `exam_event_logs` into a table named `candidate_log`. 

### Table Schema: `public.candidate_log`

| Column Name | SQL Data Type | Nullable | Description / Value Range |
| :--- | :--- | :--- | :--- |
| `log_id` | `integer` | `not null` | Source log identifier. Unique ONLY when combined with `candidate_id`. |
| `candidate_id` | `text` | `not null` | Unique candidate identifier (base64 encoded text). |
| `logged_at` | `timestamp` | `not null` | Telemetry timestamp (e.g., `2025-09-23 09:00:10.056000`). |
| `subject_id` | `text` | `nullable` | Subject slot identifier. (Contains 1 unique subject slot). |
| `candidate_status` | `text` | `nullable` | Progress text indicating current screen (e.g., `"Section 2 Question 18"`). |
| `question_display_id` | `text` | `nullable` | Question number within the section (1–25). |
| `activity` | `text` | `not null` | Event type: `"Auto Save"`, `"Mark for Review & Next"`, `"UnMark for Review & Next"`. |
| `question_response` | `text` | `nullable` | Selected option label (`"A"`, `"B"`, `"C"`, `"D"`). NULL for review marks. |
| `all_options` | `text` | `nullable` | Comma-separated available options (e.g., `"A,B,C,D"`). |
| `question_language` | `text` | `nullable` | Active question language (`"EN"` or `"HI"`). |
| `question_section` | `text` | `nullable` | Section ID (`"1"`, `"2"`, `"3"`, `"4"`). |
| `question_type` | `text` | `nullable` | Type of question (`"MCQ"` or `"Comprehension"`). |

### Indexes (Pre-existing in dump)
* `candidate_id_idx` btree (`candidate_id`)
* `candidate_id_logged_at_idx` btree (`candidate_id`, `logged_at`)

---

## 2. Data Limitations & Cleaning Assumptions

Before writing analytical queries, we analyzed the raw data distribution to establish data cleaning and filtering rules:

1. **Auto Save Events (90.73%)**:
   - Total database records: **8,246,901 rows**.
   - `Auto Save` events make up **7,482,437 rows (90.73%)**.
   - **Verification**: `SELECT COUNT(question_response) FROM candidate_log WHERE activity = 'Auto Save';` returns exactly `7,482,437`. This confirms `Auto Save` has 100.0% non-null response values. It represents the saved option state at a specific timestamp.
   - **Rule**: Do not treat every single row as a manual click. Multiple consecutive `Auto Save` events on the same question can be generated when a user changes option selections, switches languages, or during periodic autosave triggers.

2. **Null Values in `question_response`**:
   - **Verification**: Only the `question_response` column contains null values (exactly 764,464 nulls).
   - **Correlation**: The total count of `Mark for Review & Next` (536,510) and `UnMark for Review & Next` (227,954) equals exactly **764,464**.
   - **Rule**: A NULL response corresponds 100% to review actions. For option state tracking, we look only at the `Auto Save` activity type.

3. **Session Durations**:
   - The time limit of the exam is **60 minutes** (1 hour). We estimated the exam duration as the time between the candidate's first and last logged event.
   - **Rule**: If consecutive event timestamps show a gap greater than 5 minutes (300 seconds), we cap the estimated time spent at 300 seconds to prevent idle outliers from skewing question-level metrics.

---

## 3. SQL Data Aggregation & Processing Queries

All analytical findings and visualizations were generated using highly-optimized SQL queries. Below are the specific queries and logic:

### A. Candidate-Level Metadata Aggregation
We created candidate-level aggregates to extract exam duration, start/end sections, activity counts, and language toggles:
```sql
WITH candidate_times AS (
    SELECT candidate_id,
           MIN(logged_at) as first_event,
           MAX(logged_at) as last_event,
           COUNT(*) as total_events,
           SUM(CASE WHEN activity = 'Auto Save' THEN 1 ELSE 0 END) as auto_saves,
           SUM(CASE WHEN activity = 'Mark for Review & Next' THEN 1 ELSE 0 END) as marks,
           SUM(CASE WHEN activity = 'UnMark for Review & Next' THEN 1 ELSE 0 END) as unmarks,
           COUNT(DISTINCT question_section) as num_sections,
           COUNT(DISTINCT question_section || '_' || question_display_id) as num_questions,
           COUNT(DISTINCT question_language) as num_languages
    FROM candidate_log
    GROUP BY candidate_id
),
first_events AS (
    SELECT DISTINCT ON (candidate_id) candidate_id, question_section as start_section, question_language as start_lang
    FROM candidate_log
    ORDER BY candidate_id, logged_at ASC
),
last_events AS (
    SELECT DISTINCT ON (candidate_id) candidate_id, question_section as end_section
    FROM candidate_log
    ORDER BY candidate_id, logged_at DESC
)
SELECT ct.*, fe.start_section, fe.start_lang, le.end_section
FROM candidate_times ct
JOIN first_events fe ON ct.candidate_id = fe.candidate_id
JOIN last_events le ON ct.candidate_id = le.candidate_id;
```

### B. Time Spent per Section & Question Type
To estimate the time spent on questions without navigation events, we calculated the chronological lead time (time until the next event) partitioned by candidate, and grouped by question metadata:
```sql
WITH event_gaps AS (
    SELECT candidate_id, question_section, question_type, logged_at,
           LEAD(logged_at) OVER (PARTITION BY candidate_id ORDER BY logged_at) as next_logged_at
    FROM candidate_log
),
gaps_seconds AS (
    SELECT question_section, question_type,
           EXTRACT(EPOCH FROM (next_logged_at - logged_at)) as gap_sec
    FROM event_gaps
    WHERE next_logged_at IS NOT NULL
)
SELECT question_section, question_type,
       AVG(CASE WHEN gap_sec <= 300 THEN gap_sec ELSE 300 END) as avg_time_sec,
       COUNT(*) as total_events
FROM gaps_seconds
GROUP BY question_section, question_type
ORDER BY question_section, question_type;
```

### C. Answer Fickleness (Response Switching)
To measure how often candidates changed their minds, we counted how many unique answers (A–D) were selected for each question by each candidate:
```sql
WITH question_responses AS (
    SELECT candidate_id, question_section, question_display_id,
           COUNT(DISTINCT question_response) as distinct_responses
    FROM candidate_log
    WHERE activity = 'Auto Save'
    GROUP BY candidate_id, question_section, question_display_id
)
SELECT distinct_responses, COUNT(*) as count
FROM question_responses
GROUP BY distinct_responses;
```

We also calculated the raw chronological switches (e.g., A -> B -> A) by comparing a save event with its immediately preceding save event:
```sql
WITH consecutive_saves AS (
    SELECT candidate_id, question_section, question_display_id, question_response, logged_at,
           LAG(question_response) OVER (PARTITION BY candidate_id, question_section, question_display_id ORDER BY logged_at) as prev_response
    FROM candidate_log
    WHERE activity = 'Auto Save'
)
SELECT COUNT(*) 
FROM consecutive_saves 
WHERE prev_response IS NOT NULL AND question_response != prev_response;
```

### D. Section Navigation Transitions
We calculated the jumps between sections chronologically using lead/lag window functions:
```sql
WITH section_seq AS (
    SELECT candidate_id, question_section, logged_at,
           LAG(question_section) OVER (PARTITION BY candidate_id ORDER BY logged_at) as prev_section
    FROM candidate_log
)
SELECT prev_section, question_section, COUNT(*)
FROM section_seq
WHERE prev_section IS NOT NULL AND prev_section != question_section
GROUP BY prev_section, question_section
ORDER BY count DESC;
```
