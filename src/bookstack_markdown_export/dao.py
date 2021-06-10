"""
SQL Queries
"""
from typing import List

import mysql.connector
from mysql.connector.abstracts import MySQLConnectionAbstract, MySQLCursorAbstract
from pydantic import BaseModel

GET_ALL_PAGES = """
SELECT s.name, b.name, p.name, p.markdown, p.draft
FROM bookshelves s
JOIN bookshelves_books bb ON s.id = bb.bookshelf_id
JOIN books b ON b.id = bb.book_id
JOIN pages p ON b.id = p.book_id
where p.template = 0
"""


def connection(host: str, port: int, user: str, password: str, database: str):
    return mysql.connector.connect(host=host, port=port, user=user, password=password, database=database)


class PageDetails(BaseModel):
    shelf: str
    book: str
    page_title: str
    page_markdown: str
    draft: bool


def get_all_pages(conn: MySQLConnectionAbstract) -> List[PageDetails]:
    cursor: MySQLCursorAbstract
    with conn.cursor() as cursor:
        cursor.execute(GET_ALL_PAGES)
        return [
            PageDetails(shelf=shelf_name, book=book_name, page_title=page_name, page_markdown=markdown, draft=draft)
            for shelf_name, book_name, page_name, markdown, draft in cursor
        ]
