vertex(X) :- arg(X).
vertex(X) :- att(X,_).
vertex(X) :- att(_,X).
edge(X,Y) :- att(X,Y).

#show vertex/1.
#show edge/2.

