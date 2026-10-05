# Montée en capacité de la première pièce : protocole déclaré

Base gelée : 8a969f5a399f82b703142df073dac9d811ab1288.

Les paramètres neuronaux, partitions et mises à jour restent sur S².
Ce travail distingue une capacité configurable d'une capacité d'apprentissage mesurée.
Il ne démontre ni une représentation apprise, ni un avantage de S² sur un réseau euclidien.

## Couverture et ressources

Le service optionnel ScalableActionService garde des labels réellement observés
par action, feuille et contexte. Chaque compartiment conserve K résultats au plus.
La calibration conserve séparément ses 256 résultats récents par contexte.
L'âge est mesuré en révisions du modèle ; les résultats trop anciens ne comptent plus.

La réserve de couverture vaut T×L×N×K, ajoutée à celle de l'apprenant :
(L+3)W+4TC+S+T lignes/entrées de métadonnées.
Les deux réserves doivent ensemble respecter record_budget avant toute banque neuronale.
Les points S² appris gardent la réserve N(8L+2)+2L.
Ces unités sont des réserves algorithmiques, pas une garantie de RAM en octets.

Vérifications : 32 actions atteignent chacune 32 résultats observés avec C=256 ;
vieillissement, contextes distincts, partition des vrais labels, doublons,
échec privé, annulation, publication atomique, reprise JSON en partition/replay,
import v3 avec une requête en attente. Un import ne fabrique aucun résultat passé :
la couverture repart à la révision de l'import.

## Capacités et coûts

Les maxima 8 contextes, 64 symboles, 8 feuilles et profondeur 4 deviennent des
valeurs par défaut du moteur d'actions. Les capacités demandées sont contrôlées
par les réserves avant allocation. Les anciens moteurs gardent leurs contrats.

L'ingestion de 32 contextes et 256 symboles et sa reprise sont vérifiées.
Une topologie synthétique de profondeur 1 100 contrôle l'absence de récursion
dans la validation d'arbre ; elle n'est pas une démonstration d'apprentissage
de 1 100 distinctions.

Le traitement d'un résultat ne recalcule plus les prévisions des N actions
quand seule la probabilité de l'action exécutée est nécessaire.
Comparaison au code gelé : 2 048 épisodes à 8/32/128 actions, mêmes observations,
poids et RNG finaux exactement égaux. Les temps CPU sont publiés sans garantie.
Le service est comparé au moteur direct sur 4 096 épisodes à 32 actions,
avec quotas de 128 et reprises de phases.

## Situations à plusieurs états

Deux familles : huit états/huit actions et seize états/32 actions.
Trois graines 0, 1, 2, répliquées sous Windows et Linux.
Un état du monde choisit deux symboles parmi quatre et émet la séquence a,b,a,b,
après zéro à huit symboles distracteurs. Seuls les symboles opaques et la fin
d'épisode sont transmis ; aucun identifiant d'état ni action correcte n'est fourni.
Une action différente est correcte pour chaque état. Après inversion,
l'action correcte devient N−1−état. L'exploration uniforme est externe.

Le cœur dispose de 32 feuilles, profondeur 12, 32 contextes et 256 symboles,
avec record_budget=1 000 000 ; seize contextes sont rencontrés en entraînement.
Chaque cas conserve les durées suivantes, même s'il échoue :

| Phase | Résultats |
|---|---:|
| Bruit initial | 2 048 |
| Signal | 262 144 |
| Interruption bruitée | 32 768 |
| Reprise du signal | 32 768 |
| Inversion | 262 144 |

Total : 591 872 résultats par cas. Les courbes sont relevées tous les 32 768
résultats. Les reprises conservent tout l'état. Chaque évaluation contient
16 épisodes par état, sur des copies qui n'apprennent pas, en trois modes :
préfixes ordinaires, préfixes de 64 symboles et contexte non entraîné.

Critères : aucune admission sous bruit initial ou interruption ; Brier de
la seconde moitié du bruit ≤0,28 ; politique ≥90 % après signal, bruit, reprise
et inversion dans les trois modes ; Brier ≤0,05 après reprise ; révision réelle
des poids et respect des réserves. Les résultats insuffisants restent des échecs,
sans déplacer les horizons ni réduire le nombre d'états.

Ce protocole augmente la diversité des séquences et des règles d'action.
Il ne mesure ni un monde visuel, ni une mémoire temporelle arbitraire, ni
un apprentissage à 128 actions, ni des compétences générales sur PC.
