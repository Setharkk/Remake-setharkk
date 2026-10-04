# Laboratoire de la première pièce

La [première pièce](../FIRST_PIECE.md) est une mémoire qui apprend à
distinguer des contextes à partir de leur historique.

Ce dossier prépare le monde séquentiel, ses contrôles et une règle
d'admission d'une distinction proposée. Le réseau qui découvre cette
distinction n'est pas encore implémenté.

Python 3.11, bibliothèque standard uniquement :

~~~text
python -m unittest discover -s first_piece/tests -v
python -m first_piece.audit --out first_piece/lab_runs/essai_1
~~~

L'audit utilise un oracle connaissant la règle cachée. Ses résultats
valident le laboratoire et la règle d'admission ; ils ne mesurent pas
l'apprentissage d'un modèle.

Les horizons 100, 1 000 et 10 000 comptent des interactions du monde.
Le budget de 1 000 comparaisons couvre les 60 décisions de cet audit.
Il ne constitue pas un droit à poursuivre indéfiniment les mêmes tests.
