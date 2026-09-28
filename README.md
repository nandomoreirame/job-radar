# job-radar

Varre sites de vagas, descarta o que não combina com o seu perfil e publica as
compatíveis no Discord. Roda sozinho, algumas vezes por dia.

A ideia é parar de rolar lista de vaga: o que chega já passou pelos seus cortes.

**Python 3.12+, biblioteca padrão apenas.** Sem dependências para rodar; `pytest`
só para os testes.

## Como funciona

```
fontes  ──▶  filtros duros  ──▶  pontuação 0-100  ──▶  Discord
             (descarta)          (ordena)              (as melhores)
```

Os **filtros duros** respondem "eu me candidataria a isso?" e são binários. A
**pontuação** responde "quão bem isso casa comigo?" e serve para ordenar o que
sobrou. Separar os dois evita que uma vaga ruim suba por acumular pontos em
critérios secundários.

O casamento de qualificações sai do seu próprio currículo em markdown, não de uma
lista paralela. Lista paralela envelhece escondido; o currículo você mantém.

### Fontes

| Fonte | Como |
|---|---|
| Gupy | API pública do portal de empregabilidade |
| Repositórios de vagas no GitHub | API de issues (frontendbr/vagas, backend-br/vagas e afins) |
| Programathor | Listagem pública |
| Sólides Vagas | Payload do Next.js na listagem, descrição via JSON-LD da vaga |

### Filtros

Todos opcionais, configurados por variável de ambiente. Sem configuração,
nenhum deles descarta nada: é melhor um radar que deixa passar do que um que
esconde vaga por um valor que você nunca escolheu.

- **Senioridade** pelo título, com as abreviações que os anúncios realmente usam
  (`SR`, `JR/PL`, com ou sem ponto). `Pleno/Sênior` conta como sênior, porque a
  porta está aberta.
- **Modalidade**: remoto sempre passa; presencial nunca; híbrido só nas cidades
  que você listar em `COMMUTE_CITIES`.
- **Salário**, quando a vaga declara, contra um piso por tipo de contrato.
- **Qualificações**: quantos termos do seu currículo aparecem no anúncio.
- **Vagas afirmativas**, para não ocupar o lugar de quem a vaga busca. Exige a
  construção completa ("vaga exclusiva para X"), não a mera presença dos termos:
  quase todo anúncio tem um parágrafo de diversidade, e ele não restringe nada.
- **Função** pelo título, para filtrar cargos que não são o seu.
- **Linguagem**, por peso e não por presença. Um anúncio que cita Java como
  diferencial numa vaga de Python continua passando.

### Deduplicação

Cada vaga tem uma impressão digital derivada de empresa e título. O que já foi
publicado não volta ao canal, mesmo que a vaga seja reanunciada ou apareça em
duas fontes ao mesmo tempo.

### Quando não encontra nada

O canal recebe um aviso com o funil da varredura. Silêncio passa a significar
"a automação não rodou", nunca "rodou e não achou", que são problemas
completamente diferentes e indistinguíveis sem isso.

## Instalação

```bash
git clone <seu-fork> job-radar && cd job-radar
cp .env.example .env     # preencha o webhook e seus critérios
mkdir -p profile && cp /caminho/do/seu/curriculo.md profile/profile.md
```

O currículo precisa de uma seção assim, de onde saem as qualificações:

```markdown
## Stack técnica

| Área | Tecnologias |
|---|---|
| **Backend** | Python, FastAPI, PostgreSQL |
| **Frontend** | TypeScript, React, Next.js |
```

## Uso

```bash
python3 scripts/collect.py --sources gupy,github,programathor,solides
python3 scripts/triage.py --min-score 70 --top 8 --out-all data/to_send.json
python3 scripts/notify.py --input data/to_send.json --notify-empty
```

Ou os três de uma vez com `./run.sh`.

Para rodar sozinho, um timer do systemd (`systemd/` no seu fork) ou um cron
apontando para `run.sh` resolvem. Lembre de `loginctl enable-linger $USER` se
usar timer de usuário, senão ele só roda com sessão aberta.

## Testes

```bash
./scripts/setup-test-env.sh     # cria .venv e instala pytest
.venv/bin/python -m pytest tests/ -q
```

Os testes de conector usam respostas reais gravadas em `tests/fixtures/`. Vale a
disciplina: uma fixture escrita a partir do formato que você *imagina* que a API
retorna produz suíte verde com produção quebrada.

## Aviso

Cada fonte tem seus termos de uso. Os conectores respeitam `robots.txt`, se
identificam por User-Agent e colocam pausa entre requisições. Mantenha assim se
for adicionar fontes, e não use isto para candidatura automática em massa.
