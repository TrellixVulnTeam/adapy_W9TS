compile:
	conda activate condabuild && conda-build -c conda-forge -c krande . --keep-old-work --python 3.10.4

compile-docker-build:
	docker build -t ada/condabuild -f Dockerfile ../ && \
	docker run --name ada-condabuild --rm ada/condabuild

compile-docker:
	docker exec -it ada-condabuild "conda-build -c krande/label/dev -c conda-forge . --keep-old-work --python 3.9.10"

index:
	conda index ${CONDA_PREFIX}/conda-bld --channel-name local

install:
	conda create -n testenv -c local -c krande -c conda-forge ada-py --strict-channel-priority

test:
	cd ../tests && \
	pytest --doctest-modules --junitxml=junit/test-results.xml --cov=../src --cov-report=xml --cov-report=html

upload:
	conda-build -c krande -c conda-forge . --user krande

show:
	conda config --show channels

pre:
	conda create -y -n condabuild -c conda-forge conda-build conda-verify anaconda-client

py310:
	conda create -n py310 -c krande/label/dev -c conda-forge ifcopenshell h5py python==3.10.2