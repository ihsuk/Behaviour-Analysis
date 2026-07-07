# PRODIOSLABS | DATA ANALYST ASSIGNMENT
# CASE STUDY: Exam Behaviour Analysis
# Author: Khushi Pandey

import os
import getpass
import psycopg2
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Set style for premium visualization aesthetics
sns.set_theme(style="whitegrid")
plt.rcParams.update({
    'font.size': 11,
    'axes.labelsize': 12,
    'axes.titlesize': 14,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'figure.titlesize': 16,
    'figure.dpi': 300,
    'font.family': 'sans-serif'
})

# Custom cohesive color palette
PALETTE = {
    'primary': '#4A6FA5',    # Slate Blue
    'secondary': '#118AB2',  # Teal
    'accent': '#FFD166',     # Warm Yellow
    'danger': '#EF476F',     # Coral Red
    'dark': '#073B4C',       # Deep Navy
    'light': '#F8F9FA'       # Off-white
}

def run_analysis():
    # Create plots directory if it doesn't exist (using relative path)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    plots_dir = os.path.join(script_dir, "plots")
    os.makedirs(plots_dir, exist_ok=True)
    
    print("Connecting to PostgreSQL")
    conn = psycopg2.connect(
        dbname="exam_event_logs",
        user=getpass.getuser(),
        host="localhost",
        port=5432
    )
    
    
    # PLOT 1: Exam Slots & Batches (Start Time Distribution)
    
    print("Generating Plot 1: Start Time Distribution")
    query_start_times = """
        SELECT logged_at FROM (
            SELECT candidate_id, MIN(logged_at) as logged_at
            FROM candidate_log
            GROUP BY candidate_id
        ) t;
    """
    df_starts = pd.read_sql_query(query_start_times, conn)
    df_starts['logged_at'] = pd.to_datetime(df_starts['logged_at'])
    df_starts['time_only'] = df_starts['logged_at'].dt.hour + df_starts['logged_at'].dt.minute / 60.0
    
    plt.figure(figsize=(10, 5))
    n, bins, patches = plt.hist(df_starts['time_only'], bins=40, color=PALETTE['primary'], edgecolor='white', alpha=0.9)
    
    # Color active slots differently
    for patch, bin_left in zip(patches, bins[:-1]):
        if 8.8 <= bin_left <= 10.0:
            patch.set_facecolor(PALETTE['primary'])
        elif 12.3 <= bin_left <= 13.5:
            patch.set_facecolor(PALETTE['secondary'])
        elif 15.8 <= bin_left <= 17.0:
            patch.set_facecolor(PALETTE['dark'])
        else:
            patch.set_facecolor('#CED4DA')
            
    plt.title("Distribution of Candidate Start Times (Three Distinct Batches)", pad=15)
    plt.xlabel("Hour of the Day")
    plt.ylabel("Number of Candidates")
    plt.xticks([9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19], 
               ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00"])
    
    # Legend for batches
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=PALETTE['primary'], label='Batch 1: Morning (09:00)'),
        Patch(facecolor=PALETTE['secondary'], label='Batch 2: Midday (12:30)'),
        Patch(facecolor=PALETTE['dark'], label='Batch 3: Afternoon (16:00)')
    ]
    plt.legend(handles=legend_elements, loc='upper right', frameon=True, facecolor=PALETTE['light'])
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, "start_time_distribution.png"), dpi=300)
    plt.close()

    
    # PLOT 2: Time Spent by Section & Question Type
    
    print("Generating Plot 2: Time Spent per Section")
    query_time_spent = """
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
               AVG(CASE WHEN gap_sec <= 300 THEN gap_sec ELSE 300 END) as avg_time_sec
        FROM gaps_seconds
        GROUP BY question_section, question_type
        ORDER BY question_section, question_type;
    """
    df_time = pd.read_sql_query(query_time_spent, conn)
    # Combine Section and Type for label
    df_time['label'] = "Sec " + df_time['question_section'].astype(str) + "\n(" + df_time['question_type'] + ")"
    
    plt.figure(figsize=(8, 5))
    bars = plt.bar(df_time['label'], df_time['avg_time_sec'], 
                   color=[PALETTE['primary'], PALETTE['primary'], PALETTE['danger'], PALETTE['secondary'], PALETTE['primary']], 
                   edgecolor='none', alpha=0.9, width=0.6)
    
    plt.title("Average Estimated Time Spent per Event by Section & Question Type", pad=15)
    plt.ylabel("Estimated Time (Seconds)")
    plt.xlabel("Section and Question Type")
    
    # Add values on top of bars
    for bar in bars:
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2.0, height + 1.0, f'{height:.1f}s', ha='center', va='bottom', fontweight='bold')
        
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, "time_spent_by_section.png"), dpi=300)
    plt.close()

    
    # PLOT 3: Answer Fickleness (Distinct Answers selected per question)
    
    print("Generating Plot 3: Answer Fickleness")
    query_fickle = """
        WITH question_responses AS (
            SELECT candidate_id, question_section, question_display_id,
                   COUNT(DISTINCT question_response) as distinct_responses
            FROM candidate_log
            WHERE activity = 'Auto Save'
            GROUP BY candidate_id, question_section, question_display_id
        )
        SELECT distinct_responses, COUNT(*) as count
        FROM question_responses
        GROUP BY distinct_responses
        ORDER BY distinct_responses;
    """
    df_fickle = pd.read_sql_query(query_fickle, conn)
    
    labels = [f'{int(r)} Option Selected' if r == 1 else f'{int(r)} Options Selected' for r in df_fickle['distinct_responses']]
    sizes = list(df_fickle['count'])
    colors = [PALETTE['primary'], PALETTE['secondary'], PALETTE['accent'], PALETTE['danger']]
    
    fig, ax = plt.subplots(figsize=(9, 4.5))
    bars = ax.barh(labels[::-1], sizes[::-1], color=colors[::-1], edgecolor='none', alpha=0.9, height=0.5)
    
    ax.set_xscale('log')
    ax.set_title("Answer Fickleness (Distinct Option Choices Selected per Question)", pad=15)
    ax.set_xlabel("Number of Questions (Log Scale)")
    
    # Customise gridlines
    ax.grid(True, which="both", ls="--", color="#CED4DA", alpha=0.4)
    ax.set_axisbelow(True)
    
    # Add value labels next to the bars
    total_q_saves = sum(sizes)
    for bar in bars:
        width = bar.get_width()
        pct = (width / total_q_saves) * 100
        ax.text(width * 1.15, bar.get_y() + bar.get_height()/2.0, f'{width:,} ({pct:.2f}%)', 
                va='center', ha='left', fontweight='bold', fontsize=10, color='#333333')
                
    # Extend x-axis to prevent clipping labels
    ax.set_xlim(1, max(sizes) * 10.0)
    
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, "answer_fickleness.png"), dpi=300)
    plt.close()


    # PLOT 4: Starting vs Ending Sections

    print("Generating Plot 4: Starting vs Ending Sections")
    query_starts_ends = """
        WITH candidate_stats AS (
            SELECT candidate_id, MIN(logged_at) as min_t, MAX(logged_at) as max_t
            FROM candidate_log
            GROUP BY candidate_id
        ),
        start_secs AS (
            SELECT DISTINCT ON (cl.candidate_id) cl.candidate_id, cl.question_section as start_section
            FROM candidate_log cl
            JOIN candidate_stats cs ON cl.candidate_id = cs.candidate_id AND cl.logged_at = cs.min_t
        ),
        end_secs AS (
            SELECT DISTINCT ON (cl.candidate_id) cl.candidate_id, cl.question_section as end_section
            FROM candidate_log cl
            JOIN candidate_stats cs ON cl.candidate_id = cs.candidate_id AND cl.logged_at = cs.max_t
        )
        SELECT se.start_section, ee.end_section, COUNT(*) as count
        FROM start_secs se
        JOIN end_secs ee ON se.candidate_id = ee.candidate_id
        GROUP BY se.start_section, ee.end_section;
    """
    df_se = pd.read_sql_query(query_starts_ends, conn)
    
    # Group by start section and end section separately
    start_dist = df_se.groupby('start_section')['count'].sum().reset_index()
    start_dist['type'] = 'Start Section'
    start_dist.columns = ['Section', 'Count', 'Type']
    
    end_dist = df_se.groupby('end_section')['count'].sum().reset_index()
    end_dist['type'] = 'End Section'
    end_dist.columns = ['Section', 'Count', 'Type']
    
    df_plot_se = pd.concat([start_dist, end_dist])
    df_plot_se['Percentage'] = df_plot_se['Count'] / df_starts.shape[0] * 100
    
    plt.figure(figsize=(9, 5))
    ax = sns.barplot(data=df_plot_se, x='Section', y='Percentage', hue='Type', 
                     palette=[PALETTE['primary'], PALETTE['dark']])
    
    plt.title("Comparison of Starting vs Ending Section Choices", pad=15)
    plt.ylabel("Percentage of Candidates (%)")
    plt.xlabel("Question Section ID")
    
    # Add values on top of bars
    for p in ax.patches:
        height = p.get_height()
        if height > 0:
            ax.annotate(f'{height:.1f}%',
                        (p.get_x() + p.get_width() / 2., height),
                        ha='center', va='bottom', fontsize=9, fontweight='bold',
                        xytext=(0, 3), textcoords='offset points')
            
    plt.ylim(0, 85)
    plt.legend(frameon=True, facecolor=PALETTE['light'])
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, "starting_vs_ending_sections.png"), dpi=300)
    plt.close()


    # PLOT 5: Language Preference & Switchers

    print("Generating Plot 5: Language Selection Analysis")
    query_lang = """
        SELECT candidate_id, 
               COUNT(DISTINCT question_language) as distinct_langs,
               MIN(question_language) as first_lang
        FROM candidate_log
        GROUP BY candidate_id;
    """
    df_lang = pd.read_sql_query(query_lang, conn)
    
    # Categorize candidates
    def categorize_lang(row):
        if row['distinct_langs'] > 1:
            return 'Bilingual Switcher (EN & HI)'
        elif row['first_lang'] == 'EN':
            return 'English-Only (EN)'
        else:
            return 'Hindi-Only (HI)'
            
    df_lang['category'] = df_lang.apply(categorize_lang, axis=1)
    lang_counts = df_lang['category'].value_counts()
    
    plt.figure(figsize=(8, 5))
    bars = plt.bar(lang_counts.index, lang_counts.values, 
                   color=[PALETTE['primary'], '#83C5BE', PALETTE['secondary']], 
                   edgecolor='none', alpha=0.9, width=0.5)
    
    plt.title("Candidate Language Selection Patterns", pad=15)
    plt.ylabel("Number of Candidates")
    
    for bar in bars:
        val = bar.get_height()
        pct = val / df_lang.shape[0] * 100
        plt.text(bar.get_x() + bar.get_width()/2.0, val + 1000, f'{val:,}\n({pct:.1f}%)', ha='center', va='bottom', fontweight='bold')
        
    plt.ylim(0, max(lang_counts.values) * 1.15)
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, "language_selection_patterns.png"), dpi=300)
    plt.close()
    
    conn.close()
    print("All plots generated successfully!")

if __name__ == "__main__":
    run_analysis()
