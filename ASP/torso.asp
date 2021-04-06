remaining(X) :- arg(X),not backdoor(X).

% compute undirected remaining graph
undirRemain(X,Y) :- remaining(X),remaining(Y),att(X,Y).
undirRemain(X,Y) :- remaining(X),remaining(Y),att(Y,X).

% compute undirected remaining components
undirRemainComp(X,Y) :- undirRemain(X,Y).
undirRemainComp(X,Y) :- undirRemainComp(X,Z),undirRemain(Z,Y).
undirRemainComp(X,X) :- remaining(X).

% compute torso
torsoEdge(X,Y) :- backdoor(X),backdoor(Y),att(X,Y),X!=Y.
torsoEdge(X,Y) :- backdoor(X),backdoor(Y),att(X,A),att(Y,B),undirRemainComp(A,B),X!=Y.
torsoEdge(X,Y) :- backdoor(X),backdoor(Y),att(A,X),att(Y,B),undirRemainComp(A,B),X!=Y.
torsoEdge(X,Y) :- backdoor(X),backdoor(Y),att(X,A),att(B,Y),undirRemainComp(A,B),X!=Y.
torsoEdge(X,Y) :- backdoor(X),backdoor(Y),att(A,X),att(B,Y),undirRemainComp(A,B),X!=Y.
torsoEdge(X,Y) :- torsoEdge(Y,X).


% check which remaining components are adjacent to which backdoor arguments
adjacenttoBackdoor(X,Y) :- remaining(X), backdoor(Y),att(X,Y).
adjacenttoBackdoor(X,Y) :- remaining(X), backdoor(Y),att(Y,X).
adjacenttoBackdoor(X,Y) :- remaining(X), backdoor(Y), remaining(Z), undirRemainComp(X,Z), adjacenttoBackdoor(Z,Y).


%#show backdoorsize/1.
%#show backdoor/1.
%#show undirRemainComp/2.
#show torsoEdge/2.
#show adjacenttoBackdoor/2.
#show backdoor/1.
%#show remaining/1.
%#show undirRemain/2.
