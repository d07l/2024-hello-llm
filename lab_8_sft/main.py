"""
Laboratory work.

Fine-tuning Large Language Models for a downstream task.
"""
# pylint: disable=too-few-public-methods, undefined-variable, duplicate-code, unused-argument, too-many-arguments
from pathlib import Path
from typing import Iterable, Sequence
from datasets import load_dataset
import pandas as pd
from pandas import DataFrame
import torch
from torch.utils.data import DataLoader, Dataset

from core_utils.llm.raw_data_importer import AbstractRawDataImporter
from core_utils.llm.raw_data_preprocessor import AbstractRawDataPreprocessor, ColumnNames
from core_utils.llm.time_decorator import report_time
from core_utils.llm.llm_pipeline import AbstractLLMPipeline
from core_utils.llm.task_evaluator import AbstractTaskEvaluator
from core_utils.llm.metrics import Metrics
from transformers import BertForSequenceClassification, BertTokenizerFast
from torchinfo import summary
from transformers import AutoTokenizer
from config.lab_settings import SFTParams
from core_utils.llm.sft_pipeline import AbstractSFTPipeline
from peft import get_peft_model, LoraConfig


class RawDataImporter(AbstractRawDataImporter):
    """
    Custom implementation of data importer.
    """

    @report_time
    def obtain(self) -> None:
        """
        Import dataset.
        """
        self._raw_data = load_dataset(self._hf_name, split='train').to_pandas()

        if not isinstance(self._raw_data, pd.DataFrame):
            raise TypeError('Downloaded dataset is not pd.DataFrame')


class RawDataPreprocessor(AbstractRawDataPreprocessor):
    """
    Custom implementation of data preprocessor.
    """

    def analyze(self) -> dict:
        """
        Analyze preprocessed dataset.

        Returns:
            dict: dataset key properties.
        """
        return {
            'dataset_number_of_samples': len(self._raw_data),
            'dataset_columns': len(self._raw_data.columns),
            'dataset_duplicates': int(self._raw_data.duplicated().sum()),
            'dataset_empty_rows': self._raw_data.isnull().any(axis=1).sum(),
            'dataset_sample_min_len': self._raw_data['content'].dropna().map(len).min(),
            'dataset_sample_max_len': self._raw_data['content'].dropna().map(len).max()
        }

    @report_time
    def transform(self) -> None:
        """
        Apply preprocessing transformations to the raw dataset.
        """
        self._data = self._raw_data.drop(columns=["part", "movie_name", "review_id", "author", "date", "title", "grade10"], axis=1)
        self._data = self._data.rename(columns={"grade3": ColumnNames.TARGET.value, "content": ColumnNames.SOURCE.value})
        self._data = self._data.dropna()
        self._data[ColumnNames.TARGET.value] = self._data[ColumnNames.TARGET.value].map({"Good": 1, "Bad": 2, "Neutral": 0})
        self._data = self._data.reset_index(drop=True)


class TaskDataset(Dataset):
    """
    A class that converts pd.DataFrame to Dataset and works with it.
    """

    def __init__(self, data: pd.DataFrame) -> None:
        """
        Initialize an instance of TaskDataset.

        Args:
            data (pandas.DataFrame): Original data
        """
        self._data = data

    def __len__(self) -> int:
        """
        Return the number of items in the dataset.

        Returns:
            int: The number of items in the dataset
        """
        return len(self._data)

    def __getitem__(self, index: int) -> tuple[str, ...]:
        """
        Retrieve an item from the dataset by index.

        Args:
            index (int): Index of sample in dataset

        Returns:
            tuple[str, ...]: The item to be received
        """
        return (self._data[str(ColumnNames.SOURCE)][index],)

    @property
    def data(self) -> DataFrame:
        """
        Property with access to preprocessed DataFrame.

        Returns:
            pandas.DataFrame: Preprocessed DataFrame
        """
        return self._data


def tokenize_sample(
    sample: pd.Series, tokenizer: AutoTokenizer, max_length: int
) -> dict[str, torch.Tensor]:
    """
    Tokenize sample.

    Args:
        sample (pandas.Series): sample from a dataset
        tokenizer (transformers.models.auto.tokenization_auto.AutoTokenizer): Tokenizer to tokenize
            original data
        max_length (int): max length of sequence

    Returns:
        dict[str, torch.Tensor]: Tokenized sample
    """


class TokenizedTaskDataset(Dataset):
    """
    A class that converts pd.DataFrame to Dataset and works with it.
    """

    def __init__(self, data: pd.DataFrame, tokenizer: AutoTokenizer, max_length: int) -> None:
        """
        Initialize an instance of TaskDataset.

        Args:
            data (pandas.DataFrame): Original data
            tokenizer (transformers.models.auto.tokenization_auto.AutoTokenizer): Tokenizer to
                tokenize the dataset
            max_length (int): max length of a sequence
        """

    def __len__(self) -> int:
        """
        Return the number of items in the dataset.

        Returns:
            int: The number of items in the dataset
        """

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        """
        Retrieve an item from the dataset by index.

        Args:
            index (int): Index of sample in dataset

        Returns:
            dict[str, torch.Tensor]: An element from the dataset
        """


class LLMPipeline(AbstractLLMPipeline):
    """
    A class that initializes a model, analyzes its properties and infers it.
    """

    def __init__(
        self, model_name: str, dataset: TaskDataset, max_length: int, batch_size: int, device: str
    ) -> None:
        """
        Initialize an instance of LLMPipeline.

        Args:
            model_name (str): The name of the pre-trained model.
            dataset (TaskDataset): The dataset to be used for translation.
            max_length (int): The maximum length of generated sequence.
            batch_size (int): The size of the batch inside DataLoader.
            device (str): The device for inference.
        """
        super().__init__(model_name, dataset, max_length, batch_size, device)
        self._model = BertForSequenceClassification.from_pretrained(model_name)
        self._model.to(self._device)
        self._tokenizer = BertTokenizerFast.from_pretrained(model_name)

    def analyze_model(self) -> dict:
        """
        Analyze model computing properties.

        Returns:
            dict: Properties of a model
        """
        if not isinstance(self._model, torch.nn.Module):
            raise TypeError("Wrong class of model")

        max_length = self._model.config.max_position_embeddings
        input_ids = torch.ones((1, max_length), dtype=torch.long, device=self._device)
        attention_mask = torch.ones((1, max_length), dtype=torch.long, device=self._device)

        result = summary(self._model, input_data={"input_ids": input_ids, "attention_mask": attention_mask}, device="cpu", verbose=0)

        return {
            "input_shape": {"input_ids": list(result.input_size["input_ids"]), "attention_mask": list(result.input_size["input_ids"])},
            "embedding_size": self._model.config.max_position_embeddings,
            "output_shape": result.summary_list[-1].output_size,
            "num_trainable_params": result.trainable_params,
            "vocab_size": self._model.config.vocab_size,
            "size": result.total_param_bytes,
            "max_context_length": self._model.config.max_length
        }

    @report_time
    def infer_sample(self, sample: tuple[str, ...]) -> str | None:
        """
        Infer model on a single sample.

        Args:
            sample (tuple[str, ...]): The given sample for inference with model

        Returns:
            str | None: A prediction
        """
        return self._infer_batch([sample])[0]

    @report_time
    def infer_dataset(self) -> pd.DataFrame:
        """
        Infer model on a whole dataset.

        Returns:
            pd.DataFrame: Data with predictions
        """
        dataloader = DataLoader(dataset=self._dataset, batch_size=self._batch_size)

        predictions = []

        for batch in dataloader:
            batch_predictions = self._infer_batch(batch)
            predictions.extend(batch_predictions)

        results_df = pd.DataFrame({
            "target": self._dataset.data[str(ColumnNames.TARGET)].tolist(),
            "prediction": predictions
        })

        return results_df

    @torch.no_grad()
    def _infer_batch(self, sample_batch: Sequence[tuple[str, ...]]) -> list[str]:
        """
        Infer single batch.

        Args:
            sample_batch (Sequence[tuple[str, ...]]): batch to infer the model

        Returns:
            list[str]: model predictions as strings
        """
        text_samples = [sample[0] for sample in sample_batch]

        inputs = self._tokenizer(text_samples, max_length=self._max_length, padding=True, truncation=True, return_tensors='pt').to(self._device)

        if not self._model:
            raise ValueError("There is no model")

        outputs = self._model(**inputs)
        predicted_classes = torch.argmax(outputs.logits, dim=1).tolist()
        predictions = [str(i) if i != 0 else "2" for i in predicted_classes]

        return predictions


class TaskEvaluator(AbstractTaskEvaluator):
    """
    A class that compares prediction quality using the specified metric.
    """

    def __init__(self, data_path: Path, metrics: Iterable[Metrics]) -> None:
        """
        Initialize an instance of Evaluator.

        Args:
            data_path (pathlib.Path): Path to predictions
            metrics (Iterable[Metrics]): List of metrics to check
        """

    def run(self) -> dict | None:
        """
        Evaluate the predictions against the references using the specified metric.

        Returns:
            dict | None: A dictionary containing information about the calculated metric
        """


class SFTPipeline(AbstractSFTPipeline):
    """
    A class that initializes a model, fine-tuning.
    """

    def __init__(self, model_name: str, dataset: Dataset, sft_params: SFTParams) -> None:
        """
        Initialize an instance of ClassificationSFTPipeline.

        Args:
            model_name (str): The name of the pre-trained model.
            dataset (torch.utils.data.dataset.Dataset): The dataset used.
            sft_params (SFTParams): Fine-Tuning parameters.
        """

    def run(self) -> None:
        """
        Fine-tune model.
        """
