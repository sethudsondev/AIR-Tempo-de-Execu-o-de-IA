# Benchmark de tokens

`token_benchmark.py` compara, ao longo de N turnos:

- **sem SDC**: reenviar toda a memória acumulada como texto a cada turno;
- **com SDC**: só o contexto mínimo montado por `sdc_get_context` (orçamento 500 tokens).

A pergunta de todo turno é sobre *deploy*; ~1/6 da memória interessa.

## Resultado (heurística `chars//4`, medido nesta máquina)

| Turnos | memória acumulada | sem SDC | com SDC | economia |
|---|---|---|---|---|
| 6  | pouca, quase toda relevante | 1500 | 1902 | **-27%** (SDC custa mais) |
| 12 | média | 5497 | 4805 | +13% |
| 24 | grande, maioria irrelevante | 20822 | 10618 | **+49%** |

**Leitura honesta:** o SDC não "sempre economiza". Com pouca informação
toda relevante, reenviar tudo é mais barato — o overhead do handle/prefixo
não compensa. O ganho aparece (e cresce) quando a memória acumula e a
maior parte não interessa ao turno atual, que é o caso de uma sessão
longa de projeto. O ponto de virada aqui fica por volta de 10-12 turnos.
