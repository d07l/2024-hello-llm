"""
Starter for demonstration of laboratory work.
"""
# pylint: disable= too-many-locals, undefined-variable, unused-import
from pathlib import Path
from core_utils.llm.time_decorator import report_time
from lab_7_llm.main import RawDataImporter, RawDataPreprocessor

@report_time
def main() -> None:
    """
    Run the translation pipeline.
    """
    importer = RawDataImporter('trixdade/reviews_russian')
    importer.obtain()

    preprocessor = RawDataPreprocessor(importer.raw_data)
    print(preprocessor.analyze())

    result = importer
    assert result is not None, "Demo does not work correctly"


if __name__ == "__main__":
    main()
