# EpubParser

Parses epub files (wrapper around `ebooklib` package). Extract chapter titles and their corresponding texts. Can also extract the cover image.


## Installation

You can install **epubparser** via pip:

```bash
pip install epubparser
```

## Usage

```
epubparser input.epub output.txt 
```

You can apply some arguments: 

`--skip-toc`
Skip chapters whose titles match common Table of Contents variants.

`--skip-license`
Skip chapters whose titles match common License variants.

The arguments above may not be perfect, since it depends on regex an language.

`--extract-cover`
extracts cover to covers directory. If this argument is passed, output file must be specified as `None`


## License
This project is licensed under the MIT License.

