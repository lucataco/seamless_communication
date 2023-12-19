# Prediction interface for Cog ⚙️
# https://github.com/replicate/cog/blob/main/docs/python.md
from cog import BasePredictor, Input, Path, BaseModel
import torch
import torchaudio
import numpy as np
from typing import Optional
from src.seamless_communication.inference.translator import Translator
from lang_list import (
    TEXT_SOURCE_LANGUAGE_NAMES,
    S2ST_TARGET_LANGUAGE_NAMES,
    LANGUAGE_NAME_TO_CODE,
)

AUDIO_SAMPLE_RATE = 16000.0

class Output(BaseModel):
    audio_output: Optional[Path]
    text_output: str

class Predictor(BasePredictor):
    def setup(self) -> None:
        """Load the model into memory to make running multiple predictions efficient"""
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        self.translator = Translator(
            model_name_or_card="seamlessM4T_v2_large",
            vocoder_name_or_card="vocoder_v2",
            device=device,
        )

    def predict(
        self,
        task_name: str = Input(
            description="Choose a task",
            default="S2ST (Speech to Speech translation)",
            choices=[
                "S2ST (Speech to Speech translation)",
                "S2TT (Speech to Text translation)",
                "T2ST (Text to Speech translation)",
                "T2TT (Text to Text translation)",
                "ASR (Automatic Speech Recognition)",
            ],
        ),
        input_audio: Path = Input(
            description="Provide input file for tasks with speech input: S2ST, S2TT and ASR",
            default=None,
        ),
        input_text: str = Input(
            description="Provide input for tasks with text: T2ST and T2TT",
            default=None,
        ),
        input_text_language: str = Input(
            description="Specify language of the input_text for T2ST and T2TT",
            default="English",
            choices=TEXT_SOURCE_LANGUAGE_NAMES,
        ),
        target_language_with_speech: str = Input(
            description="Set target language for tasks with speech output: S2ST or T2ST. Less languages are available for speech compared to text output.",
            choices=S2ST_TARGET_LANGUAGE_NAMES,
            default="French",
        ),
        target_language_text_only: str = Input(
            description="Set target language for tasks with text output only: S2TT, T2TT and ASR.",
            choices=TEXT_SOURCE_LANGUAGE_NAMES,
            default="French",
        ),
        max_input_audio_length: float = Input(
            description="Set maximum input audio length.", default=60.0
        ),
    ) -> Output:
        """Run a single prediction on the model"""
        task_name = task_name.split()[0]
        input_data = "/tmp/cog_input_audio.wav"
        if task_name in ["S2ST", "S2TT", "ASR"]:
            assert input_audio, f"Please provide input_audio for {task_name} task."

            arr, org_sr = torchaudio.load(str(input_audio))
            new_arr = torchaudio.functional.resample(
                arr, orig_freq=org_sr, new_freq=AUDIO_SAMPLE_RATE
            )
            max_length = int(max_input_audio_length * AUDIO_SAMPLE_RATE)
            if new_arr.shape[1] > max_length:
                new_arr = new_arr[:, :max_length]
                print(
                    f"Input audio is too long. Only the first {max_input_audio_length} seconds is used."
                )
            torchaudio.save(input_data, new_arr, sample_rate=int(AUDIO_SAMPLE_RATE))
        else:
            assert input_text, f"Please provide input_text for {task_name} task."
            assert (
                not input_text_language == "None"
            ), "Please specify language for the input_text."
            input_data = input_text

        if task_name in ["S2ST", "T2ST"]:
            target_language = target_language_with_speech
        else:
            target_language = target_language_text_only

        src_lang = LANGUAGE_NAME_TO_CODE[input_text_language] if input_text_language != "None" else None
        tgt_lang = LANGUAGE_NAME_TO_CODE[target_language]

        text_out, batched = self.translator.predict(
            input=input_data,
            task_str=task_name,
            tgt_lang=tgt_lang,
            src_lang=src_lang,
        )

        text_out = str(text_out[0])

        if task_name in ["S2ST", "T2ST"]:
            wav = batched.audio_wavs[0]
            output_path = "out.wav"
            if wav.dtype == torch.float16:
                wav = wav.to(torch.float32)

            if len(wav.size()) > 2:
                wav = wav.mean(dim=0)
                
            wav_numpy = wav.detach().cpu().numpy()
                
            torchaudio.save(output_path, torch.from_numpy(wav_numpy), sample_rate=int(AUDIO_SAMPLE_RATE))
            return Output(
                audio_output=Path(output_path), text_output=(text_out)
            )
        return Output(audio_output=None, text_output=text_out)
