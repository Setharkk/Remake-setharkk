# Recherche renouvelable : résultats et limites

**Le plafond à vie est retiré dans le nouveau mode et l'apprentissage après
bruit initial fonctionne. La rétention sous bruit et l'adaptation aux
changements minoritaires restent insuffisantes.** Les résultats ne justifient
pas encore de passer ces problèmes au coordinateur comme s'ils étaient résolus.

Moteur testé : [af0bd1d](https://github.com/Setharkk/Remake-setharkk/commit/af0bd1d201500b0bdd8e35b159b8945579ec0fd5).
[Exécution Windows et Linux](https://github.com/Setharkk/Remake-setharkk/actions/runs/37222721924).
[Protocole fixé avant exécution](RENEWABLE_SEARCH_PROTOCOL.md).
[Utilisation, formule et import des anciens états](RENEWABLE_SEARCH.md).

## Vérifications et volume

Les **104 tests** passent sous Windows (Python 3.11.9) et Linux (Python 3.11.16).
Les trois workflows historiques passent aussi : laboratoire, montée à l'échelle
et comparaison avant/après des six corrections.

Chaque moteur reçoit 1 500 000 retours appris par OS : trois graines, trois
conditions. Deux moteurs, donc 3 000 000 mises en apprentissage au total par OS.
Ce chiffre compte les retours, pas les gradients supplémentaires des ajustements.
642 points d'évaluation par OS comportent chacun 2 048 épisodes sans apprentissage,
soit **1 314 816 épisodes d'évaluation**. Les plateformes répètent les mêmes
graines ; elles ne forment pas six répétitions statistiques indépendantes.

16 symboles opaques, quatre contextes, quatre actions ; exploration uniforme,
mêmes événements et actions pour les deux moteurs. Le réseau alloue toujours
64 points S² en service, contrôle inclus, et 128 pendant une validation :
128/256 degrés de liberté intrinsèques. Aucun neurone supplémentaire au renouvellement.

## Apprendre après un budget fini épuisé

40 000 retours de bruit indépendant Bernoulli(1/4), puis 40 000 retours structurés.
Évaluation finale : 512 épisodes nouveaux par contexte.

| Graine | Tentatives renouvelables après bruit | Tentatives à la fin | Succès fini, moyenne des contextes | Succès renouvelable, chaque contexte | Admission après le retour du signal |
|---|---:|---:|---:|---:|---:|
| 0 | 87 | 89 | 25.15 % | 100 % | 8 640 retours globaux |
| 1 | 87 | 89 | 22.71 % | 100 % | 4 672 retours globaux |
| 2 | 82 | 85 | 24.41 % | 100 % | 8 896 retours globaux |

Le moteur fini atteint ses 16 tentatives sans admission et reste proche du hasard.
Le mode renouvelable admet une structure sur les tentatives 89, 89 et 85.
Les délais d'admission représentent 2 160, 1 168 et 2 224 retours par contexte ;
ils ne sont pas la date exacte du premier succès, observé sur une grille plus espacée.

**Aucune nouvelle admission observée sous bruit**, dans les trois conditions
de bruit initial et les trois phases de bruit après acquisition, pour les deux
moteurs. Ce constat sur trois graines ne constitue pas une estimation précise
d'un taux de faux positifs à vie. La borne de risque provient du budget déclaré
et des hypothèses du protocole.

## Rétention : échec pendant le bruit, récupération ensuite

20 000 retours structurés → 80 000 retours aléatoires → 40 000 retours structurés.
Les colonnes évaluent l'ancienne règle structurée, hors entraînement.

| Graine | Avant le bruit, chaque contexte | Après 80 000 retours de bruit | Première mesure de récupération |
|---|---:|---|---|
| 0 | 100 % | 0 % dans les quatre contextes | 100 % après 2 000 nouveaux retours |
| 1 | 100 % | 0 % dans les quatre contextes | 100 % après 2 000 nouveaux retours |
| 2 | 100 % | 26,76 / 24,61 / 26,56 / 20,51 % | 100 % après 2 000 nouveaux retours |

Les deux moteurs ont le même profil de succès sur ces frontières.
La première mesure de récupération correspond à 500 retours par contexte :
elle donne une borne sur une grille d'observation, pas le premier instant exact.

Le programme discret conserve les relations admises, mais les prototypes actifs
continuent d'être modifiés par les retours aléatoires. Les anciennes situations
sortent aussi des buffers récents. Renouveler la recherche ne protège donc pas
les probabilités apprises. La récupération finale ne prouve pas la rétention.

## Six changements successifs : échec du contexte modifié

280 000 retours par moteur et par graine. La règle du contexte 0 suit les
décalages 0 → 1 → 2 → 3 → 0 → 2 → 1, avec 10 000 retours par contexte et par état.
Les trois autres contextes gardent leur règle.

Pour les trois graines et les deux moteurs :

- 100 % initialement dans tous les contextes.
- 0 % dans le contexte 0 à la fin des phases de décalage non nul.
- 100 % quand sa règle initiale revient.
- 100 % dans chacun des contextes 1–3 à chaque point mesuré des changements.
- Une seule admission, celle du programme initial ; aucune exception admise.
- La 16e validation est encore en cours à la fin, avec 3 158, 3 160 et 3 159
  retours principaux dans le mode renouvelable. Cette expérience n'a donc pas
  encore consommé un second bloc ; elle expose la limite de validation avant
  celle du renouvellement.

La recherche trouve des programmes incluant le prédicat du contexte 0. Le
journal donne un blocage concret, pas seulement un score final. Exemple :
graine 0, tentative 3, au retour global 57 197 :

| Critère | Valeur |
|---|---:|
| Retours principaux | 4 096 |
| Retours des autres contextes | 12 288 |
| Borne inférieure de pertinence | 0,17138 |
| Borne inférieure d'amélioration | 0,33421 |
| Coût du programme | 0,015 |
| Gain moyen de conservation observé | +0,13614 |
| Largeur de sa borne uniforme | 0,26386 |
| Borne inférieure de conservation | −0,12772 |
| Seuil requis | strictement supérieur à −0,10 |

La pertinence et l'amélioration passent, la conservation reste indécidable.
Le résultat est clôturé comme inconclusif. La garde est conservatrice ; ce
n'est pas une preuve que la proposition est nuisible. Donner davantage de
retours à une nouvelle tentative recommence la validation au même horizon :
la session plus longue ne suffit donc pas à résoudre ce cas.
D'autres essais traversent un changement de règle et sont alors devenus
futiles ; tous les journaux sont publiés.

## Ressources, reprise et reproductibilité

Dans les neuf conditions : maximum de 16 recherches détaillées, maximum observé
de 42 décisions (borne 48), 1 024 épisodes d'ajustement retenus et 128 points
alloués avec candidats. Le maximum des tailles JSON échantillonnées est
92 324 octets sous Windows, 92 309 sous Linux. Ces tailles sont mesurées aux
points de courbe, et ne sont pas un pic exact de mémoire Python.

Les six expériences de bruit restaurent un checkpoint à la tentative 17,
bloc 2, après 32 retours principaux. **1 024 retours futurs reproduisent le
même état**, sauf durée de recherche. Les essais de changements n'ont pas de
reprise dans un second bloc, puisqu'ils n'atteignent pas la tentative 17.
Les tests vérifient séparément le cache des reçus et l'import d'une action en attente.

Windows/Linux : **63 598 valeurs numériques comparées**,
écart absolu maximal 4.441e-16, tolérance 1e−10,
zéro divergence. Durées, tailles JSON, version Python et nom du runner exclus.
Les neuf expériences durent au total 695,31 s sous Windows et 631,45 s sous Linux,
deux moteurs et évaluations inclus. Ce sont des mesures CPU de runners GitHub,
pas des performances de la RTX.

Les sorties intégrales sont conservées comme artefacts du workflow. Dans le dépôt,
elles sont découpées par condition et graine, sans suppression de valeurs :

- [Index Windows](renewable_search_results/windows/index.json)
- [Index Linux](renewable_search_results/linux/index.json)
- [Comparaison des plateformes](renewable_search_results/comparison.json)

Chaque index conserve les métadonnées et le résumé du rapport, et donne les neuf
fichiers de cas : phases, courbes par contexte, journaux externes, limites et
métriques finales. Le CLI reproduit un rapport unique avec le même contenu.

## Prochaine correction de la première pièce

Deux problèmes sont maintenant mesurés : protéger ou conserver une compétence
utile malgré des gradients ultérieurs, et permettre une décision de conservation
avec un horizon suffisant sans réutiliser le risque statistique.
La formule de validation, sa séparation des périmètres et la mémoire de compétences
doivent être étudiées ensemble ; augmenter aveuglément le seuil de tolérance ou
remettre les compteurs à zéro ne constitue pas une correction justifiée.

Restent aussi le ralentissement du pas avec l'âge, les trois prédicats maximum,
la famille de relations fournie et l'absence de comparaison euclidienne.
Le dialogue, les objectifs autonomes et les actions PC ne sont pas implémentés.
