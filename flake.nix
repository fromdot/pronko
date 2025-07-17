{
  description = "A development environment for the Korean Pronunciation Analyzer";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  # flake-utils를 사용하여 각 시스템별로 출력을 쉽게 생성
  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        # 1. 현재 시스템에 맞는 패키지 셋(pkgs)을 가져옵니다.
        pkgs = nixpkgs.legacyPackages.${system};
        
        # 2. Python 버전과 uv를 명확히 정의합니다.
        python = pkgs.python3;
        uv = pkgs.uv;
      in
      {
        # 3. `devShells.default` 라는 이름으로 개발 환경을 정의합니다.
        #    이것이 `nix develop`이 찾는 최종 경로입니다.
        devShells.default = pkgs.mkShell {
          
          # buildInputs: 빌드와 런타임 모두에 필요한 의존성
          buildInputs =
            # 모든 시스템 공통 패키지
            [
              python
              uv
              pkgs.poethepoet
              pkgs.pkg-config
            ]
            # Linux일 경우에만 mecab-ko 추가
            ++ pkgs.lib.optionals pkgs.stdenv.isLinux [
              pkgs.mecab-ko
              pkgs.mecab-ko-dic
            ]
            # macOS일 경우, 컴파일에 필요한 프레임워크 추가
            ++ pkgs.lib.optionals pkgs.stdenv.isDarwin [
              pkgs.darwin.apple_sdk.frameworks.SystemConfiguration
            ];

          # macOS에서 Homebrew 패키지를 인식하기 위한 환경 변수
          MECAB_KO_DIC_PATH = pkgs.lib.optionalString pkgs.stdenv.isDarwin "/opt/homebrew/lib/mecab/dic/mecab-ko-dic";
          
          # 셸에 진입할 때 실행되는 스크립트
          shellHook = ''
            # macOS 환경일 경우, Homebrew로 mecab이 설치되었는지 먼저 확인
            if [[ "$(uname)" == "Darwin" ]] && ! command -v mecab &> /dev/null; then
              echo "🔴 Error: MeCab is not installed via Homebrew."
              echo "          Please run 'brew install mecab mecab-ko-dic' and try again."
              exit 1
            fi

            echo "✅ Welcome to the 'pronko' development environment!"
            
            VENV_DIR=".venv"
            PYPROJECT_FILE="pyproject.toml"
            REQS_FILE="requirements.txt"

            # uv를 사용하여 가상환경 생성
            if [ ! -d "$VENV_DIR" ]; then
              echo "🐍 Creating Python virtual environment using 'uv venv'..."
              uv venv -p ${python}/bin/python $VENV_DIR
            fi
            
            source "$VENV_DIR/bin/activate"

            # pyproject.toml 파일이 존재할 때 의존성 관리 자동화
            if [ -f "$PYPROJECT_FILE" ]; then
              if [ ! -f "$REQS_FILE" ] || [ "$PYPROJECT_FILE" -nt "$REQS_FILE" ]; then
                echo "⚙️ '$PYPROJECT_FILE' is newer. Compiling dependencies to '$REQS_FILE'..."
                uv pip compile "$PYPROJECT_FILE" -o "$REQS_FILE"
              fi

              echo "📦 Syncing Python dependencies using 'uv pip sync'..."
              uv pip sync "$REQS_FILE"
            else
              echo "⚠️ Warning: $PYPROJECT_FILE not found."
            fi

            echo "🚀 Environment is ready."
          '';
        };
      }
    );
}