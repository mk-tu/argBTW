% guess
{backdoor(F) : arg(F)}.
remaining(F) :- arg(F), not backdoor(F).



% check if remaining is acyclic
:- path(X,X).
path(X,Y) :- remaining(X),remaining(Y),att(X,Y).
path(X,Y) :- remaining(Y),att(Z,Y),path(X,Z).


backdoor(X) :- att(X,X).



% minimize backdoor
backdoorsize(Y) :- #count{X:backdoor(X)}=Y.
#minimize {X:backdoorsize(X)}.


#show backdoorsize/1.
#show backdoor/1.



