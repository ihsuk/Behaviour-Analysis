-- ==============================================================================
-- PRODIOSLABS | DATA ANALYST ASSIGNMENT
-- CASE STUDY: Exam Behaviour Analysis
-- SQL Queries used for Data Processing, ETL and Aggregations
-- Author: Khushi Pandey
-- Database Name: exam_event_logs
-- Table Name: candidate_log
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. Database Verification & Basic Row Count
-- ------------------------------------------------------------------------------
-- Verify total rows restored
SELECT COUNT(*) AS total_rows 
FROM candidate_log;

-- Verify count of unique candidates
SELECT COUNT(DISTINCT candidate_id) AS unique_candidates 
FROM candidate_log;


-- ------------------------------------------------------------------------------
-- 2. Activity Type & Column Nullability Diagnostics
-- ------------------------------------------------------------------------------
-- Show distinct activities and their proportion
SELECT 
    activity, 
    COUNT(*) AS total_events, 
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM candidate_log), 2) AS percentage
FROM candidate_log 
GROUP BY activity 
ORDER BY total_events DESC;

-- Verify if question_response is non-null for all Auto Save events
SELECT 
    activity, 
    COUNT(*) AS total_events, 
    COUNT(question_response) AS non_null_responses,
    ROUND(100.0 * COUNT(question_response) / COUNT(*), 2) AS pct_non_null
FROM candidate_log 
GROUP BY activity;


-- ------------------------------------------------------------------------------
-- 3. Candidate-Level Metadata Aggregation (ETL)
-- ------------------------------------------------------------------------------
-- Compile metadata for each candidate including first/last event timestamps,
-- durations, event counts, unique question/section coverage, and start/end details.
WITH candidate_times AS (
    SELECT 
        candidate_id,
        MIN(logged_at) AS first_event,
        MAX(logged_at) AS last_event,
        COUNT(*) AS total_events,
        SUM(CASE WHEN activity = 'Auto Save' THEN 1 ELSE 0 END) AS auto_saves,
        SUM(CASE WHEN activity = 'Mark for Review & Next' THEN 1 ELSE 0 END) AS marks,
        SUM(CASE WHEN activity = 'UnMark for Review & Next' THEN 1 ELSE 0 END) AS unmarks,
        COUNT(DISTINCT question_section) AS num_sections,
        COUNT(DISTINCT question_section || '_' || question_display_id) AS num_questions,
        COUNT(DISTINCT question_language) AS num_languages
    FROM candidate_log
    GROUP BY candidate_id
),
first_events AS (
    SELECT DISTINCT ON (candidate_id) 
        candidate_id, 
        question_section AS start_section, 
        question_language AS start_lang
    FROM candidate_log
    ORDER BY candidate_id, logged_at ASC
),
last_events AS (
    SELECT DISTINCT ON (candidate_id) 
        candidate_id, 
        question_section AS end_section
    FROM candidate_log
    ORDER BY candidate_id, logged_at DESC
)
SELECT 
    ct.candidate_id,
    ct.first_event,
    ct.last_event,
    EXTRACT(EPOCH FROM (ct.last_event - ct.first_event)) / 60.0 AS duration_minutes,
    ct.total_events,
    ct.auto_saves,
    ct.marks,
    ct.unmarks,
    ct.num_sections,
    ct.num_questions,
    ct.num_languages,
    fe.start_section,
    fe.start_lang,
    le.end_section
FROM candidate_times ct
JOIN first_events fe ON ct.candidate_id = fe.candidate_id
JOIN last_events le ON ct.candidate_id = le.candidate_id;


-- ------------------------------------------------------------------------------
-- 4. Pacing Analysis: Time Spent per Section & Question Type
-- ------------------------------------------------------------------------------
-- Estimate average time spent per question by calculating chronological lead times.
-- Idle times above 5 minutes (300 seconds) are capped to prevent outliers from skewing averages.
WITH event_gaps AS (
    SELECT 
        candidate_id, 
        question_section, 
        question_type, 
        logged_at,
        LEAD(logged_at) OVER (PARTITION BY candidate_id ORDER BY logged_at) AS next_logged_at
    FROM candidate_log
),
gaps_seconds AS (
    SELECT 
        question_section, 
        question_type,
        EXTRACT(EPOCH FROM (next_logged_at - logged_at)) AS gap_sec
    FROM event_gaps
    WHERE next_logged_at IS NOT NULL
)
SELECT 
    question_section, 
    question_type,
    AVG(CASE WHEN gap_sec <= 300 THEN gap_sec ELSE 300 END) AS avg_time_seconds,
    COUNT(*) AS event_count
FROM gaps_seconds
GROUP BY question_section, question_type
ORDER BY question_section, question_type;


-- ------------------------------------------------------------------------------
-- 5. Pacing Analysis: Top 10 Most Time-Consuming Questions
-- ------------------------------------------------------------------------------
WITH event_gaps AS (
    SELECT 
        candidate_id, 
        question_section, 
        question_display_id, 
        logged_at,
        LEAD(logged_at) OVER (PARTITION BY candidate_id ORDER BY logged_at) AS next_logged_at
    FROM candidate_log
),
gaps_seconds AS (
    SELECT 
        question_section, 
        question_display_id,
        EXTRACT(EPOCH FROM (next_logged_at - logged_at)) AS gap_sec
    FROM event_gaps
    WHERE next_logged_at IS NOT NULL
)
SELECT 
    question_section, 
    question_display_id,
    AVG(CASE WHEN gap_sec <= 300 THEN gap_sec ELSE 300 END) AS avg_time_seconds,
    COUNT(*) AS event_count
FROM gaps_seconds
GROUP BY question_section, question_display_id
ORDER BY avg_time_seconds DESC
LIMIT 10;


-- ------------------------------------------------------------------------------
-- 6. Answer Fickleness (Response Switching)
-- ------------------------------------------------------------------------------
-- Count how many unique answer options (A-D) were selected per question by each candidate.
WITH question_responses AS (
    SELECT 
        candidate_id, 
        question_section, 
        question_display_id,
        COUNT(DISTINCT question_response) AS distinct_responses
    FROM candidate_log
    WHERE activity = 'Auto Save'
    GROUP BY candidate_id, question_section, question_display_id
)
SELECT 
    distinct_responses, 
    COUNT(*) AS count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS percentage
FROM question_responses
GROUP BY distinct_responses
ORDER BY distinct_responses;

-- Chronological switches: Count the instances where a response actually changed 
-- from one save event to the next on the same question.
WITH consecutive_saves AS (
    SELECT 
        candidate_id, 
        question_section, 
        question_display_id, 
        question_response, 
        logged_at,
        LAG(question_response) OVER (
            PARTITION BY candidate_id, question_section, question_display_id 
            ORDER BY logged_at
        ) AS prev_response
    FROM candidate_log
    WHERE activity = 'Auto Save'
)
SELECT COUNT(*) AS total_chronological_changes
FROM consecutive_saves 
WHERE prev_response IS NOT NULL AND question_response != prev_response;


-- ------------------------------------------------------------------------------
-- 7. Section Transitions (Navigation Jumps)
-- ------------------------------------------------------------------------------
-- Quantify candidate movements between sections chronologically.
WITH section_seq AS (
    SELECT 
        candidate_id, 
        question_section, 
        logged_at,
        LAG(question_section) OVER (PARTITION BY candidate_id ORDER BY logged_at) AS prev_section
    FROM candidate_log
)
SELECT 
    prev_section, 
    question_section, 
    COUNT(*) AS transition_count
FROM section_seq
WHERE prev_section IS NOT NULL AND prev_section != question_section
GROUP BY prev_section, question_section
ORDER BY transition_count DESC;
