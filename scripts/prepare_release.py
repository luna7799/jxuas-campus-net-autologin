"""生成发布用空白配置，绝不读取或复制本机账号。"""
import argparse
import copy
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from config import DEFAULT_CONFIG, save_config


def prepare_release(output_dir):
    config_dir = Path(output_dir) / "config"
    save_config(str(config_dir / "config.json"), copy.deepcopy(DEFAULT_CONFIG))
    shutil.copyfile(ROOT / "config" / "config.example.json",
                    config_dir / "config.example.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", nargs="?", default="dist")
    prepare_release(parser.parse_args().output_dir)
