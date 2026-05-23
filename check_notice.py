import psycopg2, json
conn = psycopg2.connect('postgresql://acchelper_user:NupeblnXQ5rXSKhyUcWOcNtYOO64Sy61@dpg-d60o2063jp1c73aa5420-a.oregon-postgres.render.com/acchelper')
cur = conn.cursor()

# 컬럼 존재 여부
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name='companies' AND column_name LIKE 'notice%'
""")
cols = [r[0] for r in cur.fetchall()]
print("notice 컬럼:", cols)

# company_id=1 의 notice 값
cur.execute("SELECT company_id, company_name, notice_active, notice_text FROM companies WHERE company_id=1")
row = cur.fetchone()
print("company 1:", row)
conn.close()
