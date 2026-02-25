import sys
try:
    import resources.views
    print("Import successful")
except SyntaxError as e:
    print(f"SyntaxError in {e.filename} at line {e.lineno}, offset {e.offset}:")
    print(e.text)
    print(" " * (e.offset - 1) + "^")
    print(e)
except Exception as e:
    print(f"Error: {e}")
