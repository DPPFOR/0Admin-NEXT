#!/usr/bin/env python3
"""Check views functionality."""

import os
from sqlalchemy import create_engine, text

def main():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("DATABASE_URL not set")
        return
    
    e = create_engine(database_url, future=True)
    print('Views check:')
    
    with e.begin() as c:
        try:
            v1 = c.execute(text('SELECT COUNT(*) FROM inbox_parsed.v_inbox_by_tenant')).scalar()
            print(f'v_inbox_by_tenant: {v1} rows')
        except Exception as e:
            print(f'v_inbox_by_tenant: ERROR - {e}')
        
        try:
            v2 = c.execute(text('SELECT COUNT(*) FROM inbox_parsed.v_invoices_latest')).scalar()
            print(f'v_invoices_latest: {v2} rows')
        except Exception as e:
            print(f'v_invoices_latest: ERROR - {e}')

if __name__ == '__main__':
    main()
