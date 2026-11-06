#!/bin/sh
# Re-render the diagrams. Needs Graphviz (dot) and, for the sequence diagram, Mermaid CLI (mmdc).
for f in 01_architecture 02_data_flow 03_grc_components; do
  dot -Tpng -Gdpi=170 $f.dot -o $f.png
  dot -Tsvg $f.dot -o $f.svg
done
mmdc -i 04_policy_to_action.mmd -o 04_policy_to_action.png -b white -s 2
mmdc -i 04_policy_to_action.mmd -o 04_policy_to_action.svg -b white
