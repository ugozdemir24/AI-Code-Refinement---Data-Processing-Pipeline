# AI-Generated Code Refactor: Scalable Data Ingestion Pipeline

## Overview

This project examines the limitations of AI-generated software development by starting with a basic AI-generated Python script and improving it through software engineering practices.

The original script imported product data from a JSON file into a MySQL database. While it was functional, it mainly handled simple use cases and lacked scalability, stronger validation, fault tolerance, duplicate handling, and better observability.

The final version refactors the script into a more reliable and scalable data ingestion pipeline.

## Purpose

The goal of this project is to show that AI-generated code can be a useful starting point, but it still needs human engineering judgment to become dependable in real-world scenarios.

This project focuses on:

* Identifying weaknesses in AI-generated code
* Improving reliability and scalability
* Applying backend and data pipeline engineering practices
* Demonstrating engineering skills beyond direct AI assistance

## Methods and Improvements

The final version includes:

* Streaming JSON processing with `ijson`
* Data validation with Pydantic
* MySQL connection pooling
* Batch insert optimization
* Retry logic with exponential backoff
* Transaction rollback handling
* Duplicate record handling with `ON DUPLICATE KEY UPDATE`
* Fallback row-by-row insert strategy
* File-based logging with `pipeline.log`
* Environment variable validation with `.env`

## Technologies Used

* Python
* MySQL
* mysql-connector-python
* ijson
* Pydantic
* Tenacity
* python-dotenv

## Usage

Install dependencies:

```bash
pip install mysql-connector-python ijson pydantic tenacity python-dotenv
```

Create a `.env` file:

```env
DB_HOST=localhost
DB_USER=root
DB_PASS=your_password
DB_NAME=your_database
```

Run the final version:

```bash
python finalversion.py
```

## Project Files

```text
aiversion.py      # Initial AI-generated version
finalversion.py   # Improved engineering-focused version
REPORT.md         # Detailed improvement report
README.md
```

## Result

The project shows how a simple AI-generated import script can be reviewed, criticized, and transformed into a more fault-tolerant, scalable, and maintainable data ingestion pipeline.
