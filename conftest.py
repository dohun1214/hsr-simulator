"""테스트에서 src 레이아웃을 별도 설치 없이 임포트하기 위한 경로 설정."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
