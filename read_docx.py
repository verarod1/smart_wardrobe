import zipfile
import xml.etree.ElementTree as ET

def extract_text(docx_path, out_path):
    text = []
    with zipfile.ZipFile(docx_path, 'r') as docx:
        xml_content = docx.read('word/document.xml')
        tree = ET.XML(xml_content)
        WORD_NAMESPACE = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        PARA = WORD_NAMESPACE + 'p'
        TEXT = WORD_NAMESPACE + 't'
        for paragraph in tree.iter(PARA):
            texts = [node.text for node in paragraph.iter(TEXT) if node.text]
            if texts:
                text.append(''.join(texts))
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(text))

if __name__ == '__main__':
    extract_text('Slayers_Вакансия_AI_ассистент_и_тестовое.docx', 'reqs.txt')
