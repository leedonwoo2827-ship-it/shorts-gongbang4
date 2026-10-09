# 제3자 구성 요소

## SuperTonic (Supertone, Inc.)

- **코드** `aside_shorts/supertonic/helper.py` — https://github.com/supertone-inc/supertonic 의 `py/helper.py` 를 가져와
  GPU 공급자를 직접 받도록 조금 고쳤다. **MIT License**, Copyright (c) Supertone, Inc.
- **모델·목소리** (`assets/supertonic/` — 저장소에 넣지 않고 setup.bat 이 내려받음)
  — https://huggingface.co/Supertone/supertonic-3 . **OpenRAIL 라이선스**를 따른다. 쓰기 전에 모델 카드의 이용 제한을 확인할 것.

```
MIT License

Copyright (c) Supertone, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 그 밖에 setup 이 내려받는 것 (저장소에 넣지 않음)
- Pretendard (SIL OFL 1.1), Black Han Sans · Nanum Pen Script (SIL OFL 1.1, Google Fonts)
- GSAP 3 (GreenSock Standard License)

## diagram-design (vendor/diagram-design/)
- 출처: https://github.com/cathrynlavery/diagram-design (termbook-studio 에서 가져옴, 고정 커밋은 `vendor/diagram-design/COMMIT`)
- 라이선스: MIT — 원문 `vendor/diagram-design/LICENSE`
- 쇼츠공방4 수정: 화살촉 `markerUnits="userSpaceOnUse"` 고정 크기, 화살표 라벨 배경 사각형 금지(선 옆 + 흰 후광). 내역은 COMMIT 파일 끝.
