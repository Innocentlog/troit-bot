#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Точка входа для BotHost (bothost.ru).
Платформа ищет main.py → здесь просто запускаем bot.py.
"""

import runpy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.py"), run_name="__main__")
