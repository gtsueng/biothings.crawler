import os
import xml.etree.ElementTree as ET

import requests
from scrapy.selector import Selector


def transform(doc, mappings):

    _doc = {
        "@context": "http://schema.org/",
        "@type": "Dataset"
    }

    for key, value in doc.items():
        if key in mappings:
            if isinstance(mappings[key], str):
                _doc[mappings[key]] = value
            elif callable(mappings[key]):
                _doc.update(mappings[key](value))
            else:
                raise RuntimeError()

    return dict(sorted(_doc.items()))


def pmid_to_funding(pmid):
    '''
    Use Pubmed ID to find funding information objects
    '''
    url = "https://www.ncbi.nlm.nih.gov/pubmed/" + pmid
    body = requests.get(url).text
    pattern = '//*[@id="maincontent"]/div/div[5]/div/div/div/div//h4'
    sections = Selector(text=body).xpath(pattern)

    # Section Examples:
    #
    # 0:'<h4>Publication types</h4>'
    # 1:'<h4>MeSH terms</h4>'
    # 2:'<h4>Substance</h4>'
    # 3:'<h4>Grant support</h4>'
    # 4:'<h4>Full Text Sources</h4>'
    # 5:'<h4>Medical</h4>'
    # 6:'<h4>Miscellaneous</h4>'

    grants = []
    for section in sections:
        if 'Grant support' in section.get():
            grants = section.xpath('following-sibling::ul[1]//a/text()').getall()

            # Grant String Examples:
            # 20109744
            # 0:'M01 RR000051-475611    /RR     /NCRR NIH HHS   /United States'
            # 1:'UL1 RR025780           /RR     /NCRR NIH HHS   /United States'
            # 2:'HHSN266200400029C      /AI     /NIAID NIH HHS  /United States'
            # 3:'N01 AI040029           /AI     /NIAID NIH HHS  /United States'
            # 4:'M01 RR000051           /RR     /NCRR NIH HHS   /United States'
            # 28864822
            # 0:'MR/M00919X/1                   /Medical Research Council   /United Kingdom'
            # 1:'R01 DK090554           /DK     /NIDDK NIH HHS              /United States'
            # 2:'MC_UU_12010/10                 /Medical Research Council   /United Kingdom'
            # 3:'MC_UU_12009/15                 /Medical Research Council   /United Kingdom'
            # 4:'G0901149                       /Medical Research Council   /United Kingdom'
            # 5:'R01 DK095112           /DK     /NIDDK NIH HHS              /United States'
            # 6:'U42 OD012210           /OD     /NIH HHS                    /United States'
            # 7:'                               Wellcome Trust              /United Kingdom'
            # 8:'MC_UU_12009/6                  /Medical Research Council   /United Kingdom'

    funding = []
    for grant in grants:

        segments = grant.rsplit('/', 2)
        segments = segments[:-1]  # remove country

        if len(segments) == 1:  # only 2 sections, no identifier
            organization = segments[-1]
            identifier = None

        elif len(segments) == 2:  # more than 2 sections
            organization = segments[-1]
            subsegments = segments[0].rsplit('/', 1)

            c_1 = len(subsegments) == 2  # more than 3 segments
            c_2 = len(subsegments[-1]) == 2  # ending with 2 characters
            c_3 = subsegments[-1].isupper()  # ending with uppercases

            if c_1 and c_2 and c_3:
                identifier = segments[0][:-3]  # remove abbreviation
            else:
                identifier = segments[0]

        _doc = {
            'funder': {
                '@type': 'Organization',
                'name': organization
            },
        }
        if identifier:
            _doc['identifier'] = identifier

        funding.append(_doc)

    return funding


def pmid_to_citation(pmid):
    '''
    Use pmid to find citation string
    '''
    url = 'https://www.ncbi.nlm.nih.gov/sites/PubmedCitation?id=' + pmid
    body = requests.get(url).text
    citation = Selector(text=body).xpath('string(/)').get()
    return citation.replace(u'\xa0', u' ')

EUTILS_URL_TEMPLATE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={id}&retmode=xml&api_key={api_key}"

def pmid_with_eutils(pmid):
    '''
    Use pmid to retrieve both citation and funding info
    '''
    url = EUTILS_URL_TEMPLATE.format(id=pmid, api_key=os.environ['API_KEY'])
    body = requests.get(url).text
    root = ET.fromstring(body)

    assert root

    # funding field

    grants = []
    for grant_element in root.findall('.//Grant'):

        grant = {}
        if grant_element.find('Agency') is not None:
            grant['funder'] = {
                '@type': 'Organization',
                'name': grant_element.find('Agency').text
            }

        if grant_element.find('GrantID') is not None:
            grant['identifier'] = grant_element.find('GrantID').text

        if grant:
            grants.append(grant)

    # citation field
    citation = ''

    ## author string

    authors = []
    for author in root.findall('.//Author'):
        lastname = author.find('LastName').text
        initials = author.find('Initials').text
        authors.append(f"{lastname} {initials}")

    if len(authors) > 4:
        string = ', '.join(authors[:4])
        string += ' et al. '
        citation += string

    elif len(authors) > 1:
        string =  ', '.join(authors)
        string += '. '
        citation += string

    elif len(authors) == 1:
        citation += authors[0]
        citation += '. '

    ## the remaining string

    features = (
        ('.//MedlineCitation/Article/ArticleTitle', '{} '),
        ('.//MedlineCitation/MedlineJournalInfo/MedlineTA', '{} '),
        ('.//MedlineCitation/Article/Journal/JournalIssue/PubDate/Year', '{} '),
        ('.//MedlineCitation/Article/Journal/JournalIssue/PubDate/Month', '{};'),
        ('.//MedlineCitation/Article/Journal/JournalIssue/Volume', '{}'),
        ('.//MedlineCitation/Article/Journal/JournalIssue/Issue', '({})'),
        ('.//MedlineCitation/Article/Pagination/MedlinePgn', ':{}'),
    )

    for feature, template in features:
        if root.find(feature) is not None:
            text = root.find(feature).text
            citation += template.format(text)

    return grants, citation



# pprint(pmid_to_funder("20109744"))
# print(pmid_to_citation("20109744"))
# print(pmid_with_eutils("20109744"))