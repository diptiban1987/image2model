from core.inference.triposr import TripoSR

class ModelManager:
    def __init__(self, model_name="triposr"):
        if model_name == "triposr":
            self.engine = TripoSR()
        else:
            raise ValueError("Unsupported model")

    def run(self, image_path):
        return self.engine.generate(image_path)
