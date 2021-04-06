vertex(X) :- backdoor(X).
vertex(X) :- torsoEdge(X,_).
vertex(X) :- torsoEdge(_,X).
edge(X,Y) :- torsoEdge(X,Y).

#show vertex/1.
#show edge/2.

