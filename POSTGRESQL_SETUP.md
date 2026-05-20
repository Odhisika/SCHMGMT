# PostgreSQL Setup Guide

## 1. Install PostgreSQL

```bash
sudo apt update && sudo apt install postgresql postgresql-contrib libpq-dev
```

## 2. Start and Enable PostgreSQL

```bash
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

## 3. Create Database and User

```bash
sudo -u postgres psql
```

Inside the `psql` shell:

```sql
CREATE DATABASE school_db;
CREATE USER school_user WITH PASSWORD 'your_strong_password';
GRANT ALL PRIVILEGES ON DATABASE school_db TO school_user;
ALTER DATABASE school_db OWNER TO school_user;
\q
```

## 4. Configure `.env`

Set the following in your server `.env` file:

```
USE_POSTGRESQL=True
DB_NAME=school_db
DB_USER=school_user
DB_PASSWORD=your_strong_password
DB_HOST=localhost
DB_PORT=5432
```

## 5. Install Python PostgreSQL Adapter

Already included in `requirements.txt` (`psycopg2-binary`). If not installed:

```bash
pip install psycopg2-binary
```

## 6. Run Migrations

```bash
python manage.py migrate
```

## 7. Verify Connection

```bash
python manage.py dbshell
```

Should connect to PostgreSQL without errors.
