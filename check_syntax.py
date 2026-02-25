import sys
try:
    import result.models
    print("Import successful")
except Exception as e:
    import traceback
    traceback.print_exc()
except SyntaxError as e:
    import traceback
    traceback.print_exc()
