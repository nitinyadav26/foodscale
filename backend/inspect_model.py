try:
    import tflite_runtime.interpreter as tflite
except ImportError:
    try:
        import tensorflow.lite as tflite
    except ImportError:
        print("Neither tflite_runtime nor tensorflow is installed.")
        exit(1)

import zipfile

model_path = "../model.tflite"

try:
    interpreter = tflite.Interpreter(model_path=model_path)
    interpreter.allocate_tensors()

    print("Model loaded successfully.")

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    print("\nInput Details:")
    for i, detail in enumerate(input_details):
        print(f"[{i}] {detail}")

    print("\nOutput Details:")
    for i, detail in enumerate(output_details):
        print(f"[{i}] {detail}")

except Exception as e:
    print(f"Error loading model: {e}")
