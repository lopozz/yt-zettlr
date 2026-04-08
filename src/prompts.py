CHAPTER_TITLE_PROMPT = """
<context>
{context}
</context>

Task:
Split the context into ordered chapters.

Rules:
- Output only the chapters.
- Start each line with a dash (-)
- One line per chapter.
- Use short title descriptions.
- Do not add markdown.
- Every line must start with "Chapter X: "

Exact output format:
Chapter 1: <short_title_description>
Chapter 2: <short_title_description>
Chapter 3: <short_title_description>

Chapters:
"""

CHAPTER_ID_PROMPT = """Task:
Find the start_id for each chapter.

Rules:
- You must return exactly one existing start_id for each chapter.
- The start_id must be the first segment where a chapter begins.
- Chapters are ordered
- Do not modify the number of chapters
- Do not add explanation.
- Do not add any extra text.
- Do not add markdown.
- Use the exact format below.
- Every line follwo this format "Chapter X: [start_id]"

<context>
{context}
</context>

Chapters:
{chapters}
"""
IDEA_PROMPT = """Task:
Identify a concise numbered list of relevant ideas with important facts in the chapter.
Only the things to remember.

Rules:
- One line per idea.
- Just notions from the chapter
- Do not add explanation.
- Do not add any extra text.
- Do not add markdown.
- Use the exact format below.

Chapter title: {title}

{context}

"""

IDEA_TITLE_PROMPT = """Task:
Give the key takeaway a short title.

Rules:
- Make it brief and focused.
- Do not add explanation.
- Do not add any extra text.
- Do not use markdown.

{context}

Takeaway: {title}

Title: 
"""


IDEA_ID_PROMPT = """### Role
You are a precise information retrieval assistant. Your task is to identify the [id] of segments that provide direct context, evidence, or explanation for a specific "Takeaway."

### Criteria for Selection
Select a segment ONLY if it:
1. Explains the "how" or "why" of the Takeaway.
2. Provides a specific example or data point for the Takeaway.
3. Defines a key term used in the Takeaway.
4. States a direct consequence or condition related to the Takeaway.

Exclude segments that are only tangentially related or mention the same keywords without adding depth.

### Output Format
- Return the IDs as ID ranges (e.g.  65-87) and isoltaed comma-separated IDS (e.g., 24, 106).
- Do not include any comment, text, markdown, note or explanations.

### Example
Takeaway: Remote work increases employee retention.
Context: [0] Managers like office culture. [1] Flexible schedules reduce burnout. [2] Statistics show 30% lower quit rates for remote staff. [3] Coffee is free in the breakroom.
Output: 1, 2

### Task
Takeaway: {concept}

Context:
{context}

Output:"""
