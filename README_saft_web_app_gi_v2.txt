Dashboard SAF-T Web App GI - Versão 2

Novidade desta versão:
- nova aba "Art./Fam. por hora"
- matriz de análise por hora para artigos ou famílias
- ranking visual do top da hora selecionada
- exportação CSV da matriz por hora e do top da hora

Como arrancar:
1. Instalar dependências:
   python -m pip install -r requirements_saft_web_app_gi.txt

2. Executar:
   python -m streamlit run saft_web_app_gi_v2.py

Notas:
- a aba "Art./Fam. por hora" mostra nas linhas os artigos ou famílias e nas colunas as horas do dia
- a métrica pode ser Valor ou Quantidade
- o ranking da direita mostra os artigos/famílias mais fortes na hora escolhida
