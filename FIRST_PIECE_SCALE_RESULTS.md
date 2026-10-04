# Première pièce partagée : résultats de montée à l’échelle

La première pièce apprend les règles synthétiques prévues avec une banque S² commune aux contextes. Les trois échelles atteignent 100 % de réussite dans les évaluations finales, y compris après un changement caché et dans un contexte neuf. Ce résultat porte sur une famille de relations programmée, un alphabet discret et des actions explorées uniformément ; il ne démontre ni autonomie générale ni avantage de la courbure.

Les **85 tests passent sous Windows et Linux**. La [définition du modèle](FIRST_PIECE_SCALE.md) donne les formules, les interfaces et les instructions Windows. Le [protocole](SCALING_PROTOCOL.md) conserve les budgets, les hypothèses et les révisions effectuées à partir des défauts observés.

## Sources et preuves

- Modèle testé : [5745cb5](https://github.com/Setharkk/Remake-setharkk/commit/5745cb5f77b138cac341f7ade925757d55255e19).
- [Expérience de montée à l’échelle](https://github.com/Setharkk/Remake-setharkk/actions/runs/37214331488), réussie sur les deux systèmes.
- [Vérifications des références et de l’intégration](https://github.com/Setharkk/Remake-setharkk/actions/runs/37214331510), réussies sur les deux systèmes.
- Validation indépendante : [source fa83c8c](https://github.com/Setharkk/Remake-setharkk/commit/fa83c8cb3d99e310febfb9d6cf799ff71bcbab48), [exécution réussie](https://github.com/Setharkk/Remake-setharkk/actions/runs/37214674910).
- [Agrégat](first_piece_scale_results/aggregate.json), [données Windows](first_piece_scale_results/main_windows.json), [données Linux](first_piece_scale_results/main_linux.json), [holdout et bruit Windows](first_piece_scale_results/fresh_windows.json), [holdout et bruit Linux](first_piece_scale_results/fresh_linux.json).

Les états complets avant et après changement sont dans les artifacts `first-piece-scale-windows-latest` et `first-piece-scale-ubuntu-latest` de l’expérience. Leur expiration annoncée est le 2 janvier 2027. Les rapports restent dans Git ; le CLI reproduit les états à partir des graines publiées.

## Taille et apprentissage

Chaque condition reçoit trois graines, 10 000 retours **par contexte** avant changement et 10 000 après. Seul le contexte 0 change ; son identifiant reste le même. Les autres contextes partagent initialement la même règle. Ce protocole ne donne pas une règle arbitraire différente à chacun des seize contextes.

| Échelle | Symboles | Contextes | Actions | Retours par graine | Degrés intrinsèques en service, contrôle inclus | Maximum avec validation | Épisodes mémorisés |
|---|---:|---:|---:|---:|---:|---:|---:|
| Petite | 8 | 2 | 2 | 40 000 | 64 | 128 | 512 |
| Moyenne | 32 | 8 | 4 | 160 000 | 128 | 256 | 2 048 |
| Grande | 64 | 16 | 4 | 320 000 | 128 | 256 | 4 096 |

Les paramètres alloués demeurent constants entre huit et seize contextes. La mémoire discrète augmente sous une borne configurée. Le contrôle a les mêmes points et mises à jour, avec un routage aléatoire ; l’intervention d’effacement d’ordre utilise les mêmes poids sans les bits d’ordre.

Par système : **1 560 000 interactions d’entraînement** et **3 602 968 mises à jour neuronales**, ajustements des modèles proposés et contrôles compris. Le benchmark réalise 59 904 épisodes d’évaluation, puis 55 296 autres avec les états figés. Le holdout indépendant ajoute 55 296 épisodes. Les tests, les 576 épisodes de comparaison interface/cœur sur copies et l’entraînement du contrôle de bruit sont comptés séparément.

## Temps laissé pour apprendre et s’adapter

Moyennes de réussite de la politique sur les trois graines ; la politique choisit le candidat de probabilité maximale. Les actions utilisées pour entraîner restent uniformes.

| Échelle | Avant, 100 retours/contexte | Avant, 1 000 | Avant, 10 000 | Contexte changé après 100 | Après 1 000 | Après 10 000 |
|---|---:|---:|---:|---:|---:|---:|
| Petite | 50,3 % | 100 % | 100 % | 0 % | 39,4 % | 100 % |
| Moyenne | 25,4 % | 100 % | 100 % | 0 % | 0 % | 100 % |
| Grande | 25,0 % | 100 % | 100 % | 0 % | 0 % | 100 % |

La réussite des autres contextes reste à 100 % aux horizons après changement dans les conditions moyenne et grande. Dans la petite condition, elle baisse temporairement à **57,7 % en moyenne** à 1 000 retours, avec **45,3 %** pour la graine la plus basse, puis revient à 100 %. Les poids sont réellement partagés : la rétention n’est plus une conséquence de banques indépendantes.

La nouvelle combinaison est admise après ces nombres exacts de retours du contexte changé :

| Échelle | Graines 0, 1, 2 |
|---|---|
| Petite | 4 359 ; 4 359 ; 4 359 |
| Moyenne | 8 392 ; 8 390 ; 8 396 |
| Grande | 8 365 ; 4 247 ; 8 358 |

Il s’agit du moment d’admission, pas d’une mesure de la toute première récupération possible. À seize contextes, 8 365 retours dans le contexte changé correspondent à plus de 133 000 interactions globales après le changement. Les horizons courts auraient donc donné une conclusion prématurée d’échec définitif.

## Holdout indépendant sans nouvel entraînement

Les états finaux sont restaurés ; les tirages partent de la graine 50 000 000 et ne sont pas utilisés pour ajuster ou choisir le modèle. Trois groupes sont mesurés avant et après changement : contexte 0, autres contextes et contexte neuf. Chaque groupe reçoit 1 024 épisodes par graine et échelle, soit 55 296 épisodes au total et **zéro mise à jour d’entraînement**.

Résultats après changement, moyens sur les trois graines :

| Échelle / groupe | Modèle complet | Contrôle de capacité identique | Ordre effacé |
|---|---:|---:|---:|
| Petite / changé | 100 % | 49,7 % | 48,2 % |
| Petite / autres | 100 % | 50,4 % | 51,7 % |
| Petite / neuf | 100 % | 50,4 % | 51,0 % |
| Moyenne / changé | 100 % | 25,3 % | 24,5 % |
| Moyenne / autres | 100 % | 25,7 % | 26,3 % |
| Moyenne / neuf | 100 % | 24,5 % | 25,7 % |
| Grande / changé | 100 % | 25,7 % | 24,4 % |
| Grande / autres | 100 % | 25,5 % | 24,8 % |
| Grande / neuf | 100 % | 25,0 % | 25,2 % |

Le score de Brier est la moyenne des erreurs quadratiques sur toutes les actions. Après changement, il vaut environ 0,00000423 dans la petite condition. Dans le contexte changé des conditions moyenne et grande, il vaut respectivement 0,00004753 et 0,00003517 ; dans les autres contextes, 0,00000277 et 0,000000827. Le contrôle reste autour de 0,19 avec quatre actions et 0,26 avec deux.

Un contexte neuf reprend ici la règle commune sur des symboles déjà vus. La continuité choisie par la recherche est une hypothèse de prolongement. Ce transfert ne prédit pas le comportement d’une nouvelle application, d’un nouvel alphabet ou d’une tâche inconnue.

## Bruit indépendant

Trois contrôles séparés reçoivent chacun 20 000 retours. L’action correcte est tirée indépendamment des symboles et de l’ordre. Les trois moteurs consomment leurs seize essais et **n’admettent aucune structure**. Cela n’est pas une estimation générale du taux de faux positifs.

Leur évaluation indépendante donne 25,9 % de réussite moyenne, pour 25 % attendus au hasard, et un Brier de 0,19430. Le prédicteur constant à 0,25 aurait une espérance de Brier de 0,1875 : le modèle conserve donc une variance inutile sur le bruit.

Cet entraînement ajoute 60 000 interactions et 498 880 mises à jour par système, ajustements et contrôles compris. Il est séparé du holdout sans entraînement.

## Coûts mesurés

Temps des runners GitHub, pas du PC de l’utilisateur. Python standard ; la RTX n’intervient pas. Le cœur direct inclut la recherche et l’ajustement, mais pas l’interface. L’interface est mesurée sur 64 épisodes par condition à partir d’un état déjà entraîné.

| Échelle | Cœur Windows, secondes/graine | Cœur Linux | Interface Windows, ms/épisode | Interface Linux | Checkpoint final Windows, maximum |
|---|---:|---:|---:|---:|---:|
| Petite | 4,43–4,46 | 4,37–4,41 | 1,94–2,06 | 1,89–1,92 | 27 962 octets |
| Moyenne | 20,26–20,37 | 20,09–20,27 | 2,75–2,78 | 2,60–2,63 | 265 078 octets |
| Grande | 41,67–42,67 | 40,42–41,67 | 3,00–3,09 | 2,75–2,77 | 1 589 276 octets |

La copie récursive de l’ancienne interface coûtait 53–54 ms par épisode dans la grande condition Windows et 91–92 ms sous Linux. La copie spécialisée réduit ce coût, tout en produisant les mêmes prédictions et le même état appris que le cœur direct. Les mesures viennent d’exécutions distinctes ; leur ratio n’est pas un benchmark contrôlé du matériel.

La grande condition examine au maximum **5 748 hypothèses** par recherche ; la recherche la plus lente observée prend 0,246 seconde sous Windows. Chaque condition utilise trois ou quatre essais et deux admissions. La taille JSON ne mesure pas la consommation RAM ; aucune mesure de RSS ou de VRAM n’est revendiquée.

La comparaison Windows/Linux vérifie **12 553 valeurs numériques**, avec un écart maximal de **2,66×10⁻¹⁵** et une tolérance de 10⁻¹⁰. Temps et tailles JSON sont exclus de cette parité.

## Défauts corrigés et diagnostics conservés

La validation principale est examinée une seule fois par horizon. La garde du complément est uniforme dans le temps afin d’éviter un biais quand son nombre de retours dépend de l’ordonnancement. Un contexte unique n’attend pas un complément inexistant.

La recherche étend le programme admis même quand un changement retire son gain marginal. Entre partitions de score indiscernable à 10⁻¹², elle préfère une exception dans le périmètre d’erreur déclaré. Cette dernière correction est nécessaire : le [holdout précédent](first_piece_scale_results/pre_localization_fresh_holdout.json) échouait sur le contexte neuf après changement pour deux graines de la petite condition, malgré une réussite parfaite sur les contextes observés.

Le [premier diagnostic](first_piece_scale_results/initial_diagnostic.json) conserve l’échec de recherche du XOR de trois variables et la répétition incorrecte des examens. Les rapports [Windows](first_piece_scale_results/before_transaction_optimization_windows.json) et [Linux](first_piece_scale_results/before_transaction_optimization_linux.json) conservent le coût avant optimisation. Ces résultats ne sont pas fusionnés avec la validation finale.

## Limites et prochaine expérience

La recherche reste limitée à une famille explicite de prédicats, trois variables, un pool fini et seize essais par défaut. Les gradients continuent ensuite, mais la structure ne peut plus progresser. L’état reste borné et les situations anciennes peuvent sortir de la mémoire.

La montée à l’échelle est démontrée pour des copies d’une règle commune et une exception locale. Elle ne prouve pas la gestion de seize règles indépendantes, de plusieurs flux concurrents, de retours retardés, d’images, de fichiers réels, du dialogue ou d’objectifs autonomes.

La prochaine expérience doit réduire l’oubli temporaire tout en gardant une adaptation vérifiable, puis mesurer des observations plus riches. L’avantage de S² face à un réseau euclidien de même capacité reste une question séparée.
