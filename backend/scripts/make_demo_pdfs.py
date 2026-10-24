"""Generate the demo persona's CV + curriculum PDFs into shared/demo/. Run: python scripts/make_demo_pdfs.py"""
from pathlib import Path

import pymupdf

OUT = Path(__file__).resolve().parents[2] / "shared" / "demo"

CV = """Omar Hassan
Computer Science graduate, Cairo University (2026) - Cairo, Egypt

SUMMARY
Fresh graduate interested in backend development.

PROJECTS
Graduation Project - Clinic Booking System
Built a REST API in Python using FastAPI for clinic appointment booking.
Designed a PostgreSQL schema with 12 tables and wrote complex SQL queries.

Personal Project - Expense Tracker
A small Flask web app with HTML and CSS templates to track daily expenses.

EXPERIENCE
Summer Intern - Software Team, Sample Co (2 months, 2025)
Fixed bugs in an internal Python reporting tool.

SKILLS
Python, SQL, FastAPI, HTML, CSS, problem solving
"""

CURRICULUM = """Faculty of Computers and Artificial Intelligence - Academic Transcript

CS101 Introduction to Programming (Python)    A
CS201 Object Oriented Programming (Java)      B+
CS214 Data Structures                         A-
CS301 Algorithms                              B+
CS305 Database Systems                        A
CS310 Operating Systems                       B
CS320 Computer Networks                       B
CS350 Web Programming                         A-
CS402 Software Testing                        B+
CS410 Software Engineering                    A
CS420 Introduction to Machine Learning        B
"""


def write(path: Path, text: str):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(50, 50, 560, 800), text, fontsize=10)
    doc.save(path)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    write(OUT / "demo_cv.pdf", CV)
    write(OUT / "demo_curriculum.pdf", CURRICULUM)
    print("wrote", OUT)
