"""Gera a classificação temática proposta para as votações ordinárias de 2026.

Entradas imutáveis:
- dados/brutos/contagem_votacoes_ordinarias_2026.json
- dados/brutos/materias-2026-resposta-original.csv
- dados/brutos/sessao_<id>_ordemdia.json e páginas adicionais

Saída reproduzível:
- dados/tratados/tema-votacoes-2026.csv

As regras e categorias abaixo foram propostas por IA depois da leitura das
ementas. Nenhuma classificação foi revisada por uma pessoa.
"""

import csv
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[2]
BRUTOS = RAIZ / "dados" / "brutos"
SAIDA = Path(__file__).with_name("tema-votacoes-2026.csv")
RESULTADOS_DE_VOTACAO = {"UNANIMIDADE", "MAIORIA ABSOLUTA", "REJEITADO"}

# Cada expressão recebe um peso. Termos que identificam diretamente um tema
# pesam mais que palavras que também podem ser apenas endereço ou contexto.
REGRAS = {
    "Homenagens, nomes e datas": [
        (r"\btitulo de (?:cidadao|vulto)|\bhonraria\b|\bhomenage\w*", 6),
        (r"\bdenomin\w*|denominacao\b|nomeia\w*", 6),
        (r"\butilidade publica\b", 5),
        (r"\b(?:dia|semana|mes) municipal\b|\bcalendario oficial\b", 5),
        (r"\bmocao de (?:aplausos|congratulacoes)\b|\bcongratulacoes\b", 5),
        (r"\baniversari\w*\b|\bdata comemorativa\b", 3),
    ],
    "Defesa Civil": [
        (r"\bdefesa civil\b|\bpmpdc\b|\bprotecao e defesa civil\b", 6),
        (
            r"\brisco de (?:desmoronamento|deslizamento|enxurrada)|"
            r"desmoronamento|deslizamento(?: de terra)?\b",
            6,
        ),
        (
            r"\bvistoria\s+tecnica\b.{0,80}"
            r"(?:risco|desmoron|desliz|barranco|encosta|emergenc)",
            6,
        ),
        (r"\bvistoria\s+tecnica\s+em\s+barranco\b", 6),
        (r"\b(?:situacao|estado) de (?:emergencia|calamidade)\b|\bcalamidade publica\b", 6),
        (r"\bplano\s+municipal\s+de\s+reducao\s+de\s+riscos\b|\breducao de riscos\b", 6),
        (r"\bmapeamento\s+das?\s+areas?\s+de\s+maior\s+risco\b", 6),
        (r"\balerta\s+sonor\w*.{0,50}(?:risco|enchente|desliz|alagamento)\b", 5),
        (r"\bareas?\s+de\s+risco\b|\bzona de risco\b", 5),
    ],
    "Saúde": [
        (r"\bsaude\b|\bhospital\b|\bunidade basica\b|\bubs\b|\bupa\b", 5),
        (r"\bmedic\w*|\benferm\w*|\bodont\w*|\bfarmac\w*|\bneurolog\w*", 4),
        (r"\bvacina\w*|\bpaciente\w*|\bambulancia\w*|\bfisioterap\w*", 4),
        (r"\bautismo\b|\btea\b|\bsaude mental\b|\bpsicolog\w*|\btelemedicina\b", 4),
        (r"\bdengue\b|\bcancer\b|\bdoenca\w*|\bvigilancia sanitari\w*", 4),
        (r"\bsamu\w*|\bsamuzinho\b|\bpronto atendimento\b", 4),
    ],
    "Educação": [
        (r"\beducacao\b|\bescola\w*|\bcreche\w*|\bcmei\b|\bcolegio\w*", 5),
        (r"\bensino\b|\baluno\w*|\bprofessor\w*|\bestudante\w*|\bmagisterio\b", 4),
        (r"\bpedagog\w*|\bmerenda\b|\bmaterial escolar\b", 4),
        (r"\bcemae\b|\binstituto federal\b|\bifpr\b", 4),
    ],
    "Segurança pública": [
        (r"\bseguranca publica\b|\bguarda municipal\b|\bpolici\w*", 5),
        (r"\bbombeiro\w*|\bpatrulh\w*", 4),
        (r"\bvideomonitoramento\b|\bcamera\w* (?:de )?(?:seguranca|monitoramento)\b", 4),
        (r"\bciosp\b|\bvigilancia eletr[ôo]nica\b|\bpatrulha maria da penha\b", 4),
        (r"\broubo\w*|\bfurto\w*", 3),
    ],
    "Assistência social e direitos": [
        (r"\bassistencia social\b|\bcras\b|\bvulnerab\w*", 5),
        (r"\bconselho tutelar\b|\bdireitos humanos\b|\bviolencia domestica\b", 5),
        (
            r"\bpesso\w* com deficiencia\b|\bpcd\b|\bcrianc\w* com deficiencia\b"
            r"|\bacessibilidade\b",
            4,
        ),
        (r"\bidos\w*\b|\bpesso\w* idos\w*\b|\bcrianc\w*\b|\badolescent\w*\b|\bmulher\w*", 3),
        (r"\binss\b|\bcentro de convivencia\b", 3),
        (r"\bmorador\w* de rua\b|\bigualdade racial\b|\bcomunidade indigen\w*\b|\bindigen\w*\b", 4),
    ],
    "Cultura, esporte e lazer": [
        (r"\bcultur\w*\b|\bbiblioteca\w*|\bmuseu\w*|\bartesan\w*", 5),
        (
            r"\besport\w*|\besportiv[oa]\w*|\bpoliesportiv[ao]\w*|\bquadra\w*"
            r"|\bfutebol\b|\bginasio\w*",
            5,
        ),
        (r"\bskate\b|\bvolei\b|\bcancha\b|\batletismo\b|\bpesca esportiva\b", 4),
        (r"\blazer\b|\bparque infantil\b|\bplayground\b|\bparquinho\b", 4),
        (r"\bacademia ao ar livre\b|\bcalistenia\b", 4),
        (r"\bevento\w*|\bturismo\b|\bshow\b|\bpnab\b", 3),
    ],
    "Meio ambiente e animais": [
        (r"\bmeio ambiente\b|\bambient\w*\b|\bpoluicao\b", 5),
        (r"\barboriz\w*|\barvor\w*\b|\bnascente\w*|\bparque natural\b", 4),
        (r"\brio\b|\bcorrego\w*|\brepresa\w*|\breciclag\w*|\bcoleta seletiva\b", 4),
        (r"\bresiduo\w*|\bdesassoreamento\b|\balagamento\w*|\benchente\w*", 4),
        (r"\banim\w*\b|\bveterin\w*|\bcastrac\w*\b|\bprotecao animal\b", 4),
    ],
    "Iluminação e serviços urbanos": [
        (r"\biluminacao\b|\blampad\w*\b|\bluminari\w*\b", 5),
        (r"\benergia eletric[ao]\b|\bred[ea]s? eletric[ao]s?\b", 4),
        (r"\bsaneamento\b|\besgoto\b|\bagua potavel\b|\brede de agua\b", 5),
        (r"\bdrenagem\b|\bmanilhamento\b|\bgaleri\w* pluvi\w*", 5),
        (r"\bbueiro\w*|\bboc\w* de lobo\b", 4),
        (r"\blimpeza\b|\bcoleta de lixo\b|\blixeir\w*\b|\brocad\w*\b|\bpod\w*\b", 4),
        (r"\bcemiteri\w*\b", 3),
    ],
    "Ruas, trânsito e transporte": [
        (r"\basfalt\w*\b|\basfaltic\w*|\b(?:re)?paviment\w*|\breperfilamento\b", 5),
        (r"\bpatrolamento\b|\bensaibramento\b|\bcalcad\w*\b|\bmeio-fio\b", 5),
        (r"\bponte\w*|\btravessia\w*|\bacesso viari[oa]\b|\bciclovia\w*", 4),
        (
            r"\btransito\b|\bsinalizacao(?: viari[ao])?\b|\bpintura viari[ao]\b"
            r"|\bsemafor\w*\b|\bsistema viari[oa]\b",
            5,
        ),
        (r"\bredutor\w* de velocidade\b|\blombad\w*\b", 5),
        (r"\bradar\w*|\btachinha\w*|\btach[aoõ]es\b|\btapa-buraco\w*", 5),
        (r"\bponto\w* de onibus\b|\btransporte coletivo\b|\blinha de onibus\b", 5),
        (r"\btarifa de onibus\b|\bcirculacao viari[ao]\b|\bvia rural\b", 4),
        (r"\bestacionamento\b", 4),
        (r"\binterligacao entre (?:as )?ruas\b|\babertura (?:das? )?ruas\b", 4),
        (r"\bruas?\b|\bavenid\w*\b|\bestrad\w*\b|\brodovi\w*\b", 1),
    ],
    "Desenvolvimento, moradia e agricultura": [
        (r"\bhabitacao\b|\bprograma habitacional\b|\bregularizacao fundiaria\b", 5),
        (
            r"\bdesenvolvimento economic[oa]\b|\bexploracao economic[ao]\b"
            r"|\bempreendedor\w*|\bempreg\w*\b",
            5,
        ),
        (r"\bagricultur\w*\b|\bagricol\w*\b|\bprodutor\w* rural\b", 5),
        (r"\btrabalho,? renda e qualificacao\b|\bagencia do trabalhador\b", 5),
        (r"\bcurso\w* (?:tecnic[ao]\w*|profissionalizante\w*)\b|\bqualificac\w*\b", 4),
        (r"\bfeira livre\b|\bcomercio\b|\bindustri\w*\b", 3),
    ],
    "Administração e finanças": [
        (r"\borcamento\b|\bcredito adicional\b|\bcredito especial\b", 5),
        (r"\bfinanceir\w*|\btribut\w*|\bimpost\w*\b|\btax\w*\b", 4),
        (r"\bservidor\w*|\bcarg\w*\b|\bsalari\w*\b|\bremuneracao\b", 4),
        (r"\bconcurso publico\b|\bfolha de pagamento\b|\bvantagens funcionais\b", 4),
        (r"\bestrutura administrativ\w*\b|\bcontratacao\b|\blicitacao\b", 4),
        (r"\bconvenio\w*|\bsubvencao\b|\bprevidencia\b|\bemenda impositiva\b", 4),
        (r"\bplano diretor\b|\badministracao publica\b", 4),
        (r"\baltera dispositivos\b|\brevog\w*\b|\bdesafet\w*\b", 3),
        (r"\bdoacao de imovel\b|\bcessao de uso\b", 4),
    ],
}


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = texto.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", texto).strip()


def classificar(ementa):
    texto = normalizar(ementa)
    pontos = {
        tema: sum(peso for expressao, peso in regras if re.search(expressao, texto))
        for tema, regras in REGRAS.items()
    }
    maior = max(pontos.values())
    if maior == 0:
        return "Outros"
    # A ordem explícita de REGRAS resolve empates de forma reproduzível.
    return next(tema for tema in REGRAS if pontos[tema] == maior)


def carregar_materias():
    caminho = BRUTOS / "materias-2026-resposta-original.csv"
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        return {int(linha["ID"]): linha for linha in csv.DictReader(arquivo, delimiter=";")}


def carregar_votacoes():
    contagem = json.loads(
        (BRUTOS / "contagem_votacoes_ordinarias_2026.json").read_text(encoding="utf-8")
    )
    votacoes = []
    for sessao in contagem["sessoes"]:
        itens = []
        caminhos = [
            BRUTOS / f"sessao_{sessao['id']}_ordemdia.json",
            BRUTOS / f"sessao_{sessao['id']}_ordemdia_pagina_2.json",
        ]
        for caminho in caminhos:
            if caminho.exists():
                resposta = json.loads(caminho.read_text(encoding="utf-8"))
                itens.extend(resposta["results"])

        votadas = [
            item
            for item in itens
            if item.get("resultado", "").upper() in RESULTADOS_DE_VOTACAO
        ]
        # A sessão 795 aconteceu no mesmo dia da coleta da contagem. Naquele
        # retrato ela ainda tinha zero votações; a ordem do dia baixada depois
        # já traz resultados. O universo do gráfico é o retrato de 1.388.
        if sessao["n_votacoes"] == 0:
            votadas = []
        if len(votadas) != sessao["n_votacoes"]:
            raise ValueError(
                f"Sessão {sessao['id']}: a contagem guardada é "
                f"{sessao['n_votacoes']}, mas a ordem do dia tem {len(votadas)}."
            )
        votacoes.extend(votadas)

    if len(votacoes) != contagem["total_votacoes"]:
        raise ValueError(
            f"Esperava {contagem['total_votacoes']} votações, achei {len(votacoes)}."
        )
    return votacoes


def main():
    materias = carregar_materias()
    votacoes = carregar_votacoes()
    linhas = []
    sem_ementa = Counter()

    for item in votacoes:
        materia = materias.get(item["materia"])
        if materia is None:
            sem_ementa[item["materia"]] += 1
            continue

        linhas.append(
            {
                "sessao_id": item["sessao_plenaria"],
                "item_ordem_id": item["id"],
                "resultado": item["resultado"],
                "materia_id": item["materia"],
                "numero": materia["Número"],
                "ano": materia["Ano"],
                "tipo_sigla": materia["Tipo de Matéria Legislativa/Sigla"],
                "tipo_descricao": materia["Tipo de Matéria Legislativa/Descrição"],
                "ementa": materia["Ementa"],
                "tema_proposto": classificar(materia["Ementa"]),
                "classificador": "IA, por regras temáticas documentadas",
                "revisada_por_humano": "não",
                "fonte_oficial": f"https://sapl.campolargo.pr.leg.br/materia/{item['materia']}",
            }
        )

    campos = list(linhas[0])
    with SAIDA.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=campos)
        escritor.writeheader()
        escritor.writerows(linhas)

    contagens = Counter(linha["tema_proposto"] for linha in linhas)
    print(f"{len(votacoes)} votações localizadas")
    print(f"{len(linhas)} votações classificadas")
    print(f"{sum(sem_ementa.values())} sem ementa no CSV de 2026")
    for tema, quantidade in contagens.most_common():
        print(f"{tema}: {quantidade}")


if __name__ == "__main__":
    main()
