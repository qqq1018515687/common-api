#!/usr/bin/env python3
"""创建数据库表脚本"""
import sys
sys.path.insert(0, '/workspace/projects')
sys.path.insert(0, '/workspace/projects/src')

from storage.database.shared import engine, Base
print('Creating tables...')
Base.metadata.create_all(bind=engine)
print('Tables created successfully!')
