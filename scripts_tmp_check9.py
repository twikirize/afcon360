import re
s = open('templates/kyc/index.html', encoding='utf-8').read()
opens = len(re.findall(r'{%\s*block\s', s))
ends = len(re.findall(r'{%\s*endblock\s*%}', s))
ifs = len(re.findall(r'{%\s*if\s', s))
endifs = len(re.findall(r'{%\s*endif\s*%}', s))
elses = len(re.findall(r'{%\s*else\s*%}', s))
print('blocks:', opens, ends)
print('ifs:', ifs, 'endifs:', ifdefs, 'elses:', elses)
for i, line in enumerate(s.split('\n'), 1):
    if re.search(r'{%\s*block\s', line):
        print('BLOCK START line', i, ':', line.strip())
    if re.search(r'{%\s*endblock\s*%}', line):
        print('BLOCK END line', i, ':', line.strip())
