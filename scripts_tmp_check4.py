from jinja2 import Environment
env = Environment()
t = env.from_string('{% set d = {"a":"1","b":"2"} %}{{ d["a"] }}')
print('dict literal:', repr(t.render()))

t2 = env.from_string('{% set icons = {"income_source":"bi-cash-stack"} %}{{ icons["income_source"] }}')
print('icons:', repr(t2.render()))

# Test the actual pattern used in template
t3 = env.from_string('{% for r in reqs %}{% set icons = {"income_source":"bi-cash-stack"} %}{{ icons[r] }}{% endfor %}')
print('loop+dict:', repr(t3.render(reqs=['income_source','passport'])))
