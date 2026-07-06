import os
import logging
import ijson
import mysql.connector
from mysql.connector import pooling
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)


# Load environment variables from the .env file.
# This keeps sensitive database credentials out of the source code.
load_dotenv()


# Configure logging for both console output and file-based logging.
# In a production-like environment, file logs help with debugging,
# monitoring, and post-failure investigation.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("pipeline.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)


class Product(BaseModel):
    """
    Pydantic data model for validating product records.

    This ensures that every product has:
    - a non-empty name
    - a price greater than zero

    Invalid records are rejected before they reach the database.
    """

    name: str = Field(min_length=1)
    price: float = Field(gt=0)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value):
        """
        Normalize and validate the product name.

        Leading and trailing spaces are removed.
        If the name becomes empty after stripping spaces,
        the record is considered invalid.
        """

        value = value.strip()

        if not value:
            raise ValueError("Product name cannot be empty.")

        return value


class DatabaseManager:
    """
    Handles database connection pooling and insert operations.

    Instead of opening a new database connection for every insert,
    this class uses a MySQL connection pool. Connection pooling improves
    performance under repeated database operations and reduces connection overhead.
    """

    def __init__(self):
        """
        Initialize the database connection pool.

        Before creating the pool, the code checks whether all required
        environment variables exist. This prevents unclear connection errors
        later in the pipeline.
        """

        required_envs = ["DB_HOST", "DB_USER", "DB_PASS", "DB_NAME"]
        missing_envs = [key for key in required_envs if not os.getenv(key)]

        if missing_envs:
            raise EnvironmentError(
                f"Missing environment variables: {', '.join(missing_envs)}"
            )

        self.pool = pooling.MySQLConnectionPool(
            pool_name="product_pool",
            pool_size=5,
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            database=os.getenv("DB_NAME")
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(mysql.connector.Error),
        reraise=True
    )
    def insert_batch(self, data):
        """
        Insert a batch of validated product records into the database.

        Improvements added here:
        - Uses batch insert instead of one-by-one insert for better performance.
        - Uses ON DUPLICATE KEY UPDATE to handle duplicate product names.
        - Uses retry with exponential backoff for temporary database failures.
        - Uses rollback when a database error occurs.
        - Falls back to row-by-row insert if the whole batch fails due to integrity issues.

        The retry decorator will retry MySQL-related errors up to 3 times.
        """

        if not data:
            return

        conn = self.pool.get_connection()
        cursor = conn.cursor()

        # ON DUPLICATE KEY UPDATE requires a UNIQUE constraint on the name column.
        # If a product with the same name already exists, its price will be updated
        # instead of causing the entire insert operation to fail.
        query = """
        INSERT INTO products (name, price)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE
            price = VALUES(price)
        """

        try:
            cursor.executemany(query, data)
            conn.commit()

            logging.info(
                f"Batch processed successfully. Records: {len(data)}"
            )

        except mysql.connector.IntegrityError as error:
            # IntegrityError may happen because of constraint-related problems.
            # Instead of losing the entire batch, the transaction is rolled back
            # and the system tries to insert records one by one.
            conn.rollback()

            logging.warning(
                f"Batch integrity error. Falling back to row-by-row insert. "
                f"Records: {len(data)} | Error: {error}"
            )

            self.insert_rows_safely(data)

        except mysql.connector.Error as error:
            # For other database errors, rollback the transaction and re-raise
            # the exception so the retry mechanism can handle it.
            conn.rollback()

            logging.error(
                f"Database error during batch insert. Records: {len(data)} | Error: {error}"
            )

            raise

        finally:
            # Always close the cursor and connection.
            # With connection pooling, conn.close() returns the connection
            # back to the pool instead of fully destroying it.
            cursor.close()
            conn.close()

    def insert_rows_safely(self, data):
        """
        Fallback insert strategy.

        If a full batch fails, this method tries to insert each record individually.
        This prevents one problematic row from causing the whole batch to be lost.

        This is useful for high-volume data pipelines where partial progress
        is better than failing the entire import process.
        """

        conn = self.pool.get_connection()
        cursor = conn.cursor()

        query = """
        INSERT INTO products (name, price)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE
            price = VALUES(price)
        """

        success_count = 0
        failed_count = 0

        try:
            for row in data:
                try:
                    cursor.execute(query, row)
                    success_count += 1

                except mysql.connector.Error as error:
                    failed_count += 1

                    logging.warning(
                        f"Skipped row due to database error: {row} | Error: {error}"
                    )

            conn.commit()

            logging.info(
                f"Fallback insert completed. Successful: {success_count}, Failed: {failed_count}"
            )

        except mysql.connector.Error as error:
            # If the fallback process itself fails at transaction level,
            # rollback all changes made during this fallback transaction.
            conn.rollback()

            logging.error(
                f"Fallback insert failed. Transaction rolled back. Error: {error}"
            )

            raise

        finally:
            cursor.close()
            conn.close()


def process_stream(file_path, db_manager, batch_size=1000):
    """
    Process a large JSON file using streaming.

    Instead of loading the entire JSON file into memory with json.load(),
    this function uses ijson to read items one by one.

    This makes the pipeline suitable for large files because memory usage
    stays much more stable.
    """

    if not os.path.exists(file_path):
        logging.error(f"File not found: {file_path}")
        return

    batch = []
    valid_count = 0
    invalid_count = 0

    try:
        with open(file_path, "rb") as file:
            # This expects the JSON file to be an array of objects:
            #
            # [
            #   {"name": "Product A", "price": 10.5},
            #   {"name": "Product B", "price": 25.0}
            # ]
            #
            # The "item" prefix tells ijson to stream each object inside the array.
            products = ijson.items(file, "item")

            for item in products:
                try:
                    # Validate and normalize each product before inserting it.
                    product = Product(**item)

                    batch.append((product.name, product.price))
                    valid_count += 1

                    # Once the batch reaches the defined size,
                    # insert it into the database and clear the batch.
                    if len(batch) >= batch_size:
                        db_manager.insert_batch(batch)
                        batch.clear()

                except ValidationError as error:
                    # Invalid records are logged and skipped.
                    # The pipeline continues instead of stopping completely.
                    invalid_count += 1

                    logging.warning(
                        f"Invalid product skipped: {item} | Error: {error}"
                    )

            # Insert remaining records that did not fill a complete batch.
            if batch:
                db_manager.insert_batch(batch)

        logging.info(
            f"Pipeline completed. Valid records: {valid_count}, "
            f"Invalid records: {invalid_count}"
        )

    except ijson.JSONError as error:
        # Handles malformed or invalid JSON files.
        logging.critical(f"Invalid JSON format: {error}")

    except mysql.connector.Error as error:
        # Handles database-level failures that remain after retries.
        logging.critical(f"Database operation failed after retries: {error}")

    except Exception as error:
        # Catches unexpected errors and prints the traceback.
        # logging.exception is useful because it includes stack trace information.
        logging.exception(f"Unexpected pipeline error: {error}")


if __name__ == "__main__":
    """
    Application entry point.

    Creates the database manager and starts the streaming pipeline.
    """

    database = DatabaseManager()
    process_stream("data.json", database)