import mysql.connector

import json

import logging

import os

from dotenv import load_dotenv


load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class DatabaseManager:

    def __init__(self):

        self.conn = mysql.connector.connect(

            host=os.getenv("DB_HOST"),

            user=os.getenv("DB_USER"),

            password=os.getenv("DB_PASS"),

            database=os.getenv("DB_NAME")

        )

        self.cursor = self.conn.cursor()

    def batch_insert(self, data_list):



        query = "INSERT INTO products (name, price) VALUES (%s, %s)"

        try:

            self.cursor.executemany(query, data_list)

            self.conn.commit()

            logging.info(f"{len(data_list)} kayıt başarıyla aktarıldı.")

        except mysql.connector.Error as err:

            self.conn.rollback()

            logging.error(f"Veritabanı hatası: {err}")


class DataValidator:

    @staticmethod
    def clean(raw_data):

        """Veri tipini ve içeriğini kontrol eder"""

        clean_list = []

        for item in raw_data:

            try:

                # Gelen veriyi valide et

                name = str(item['name'])

                price = float(item['price'])

                clean_list.append((name, price))

            except (KeyError, ValueError, TypeError) as e:

                logging.warning(f"Hatalı veri atlandı: {item} | Sebep: {e}")

        return clean_list


def run_pipeline(file_path):


    if not os.path.exists(file_path):
        logging.error("Dosya bulunamadı.")

        return

    try:

        with open(file_path, 'r') as f:

            raw_data = json.load(f)

        validator = DataValidator()

        validated_data = validator.clean(raw_data)

        db = DatabaseManager()

        db.batch_insert(validated_data)

        db.cursor.close()

        db.conn.close()



    except Exception as e:

        logging.critical(f"Sistem hatası: {e}")


if __name__ == "__main__":
    run_pipeline("data.json")