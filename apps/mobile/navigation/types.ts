import type { NavigationProp } from "@react-navigation/native";

export type RootStackParamList = {
  Tabs: undefined;
  Show: { eventId: string };
  Band: { handle: string };
  Search: undefined;
  SignIn: undefined;
  Join: undefined;
  Profile: { handle: string };
  ListDetail: { listId: string };
  Feed: undefined;
  Notifications: undefined;
  Classifieds: undefined;
  Gig: { gigId: string };
  PostGig: undefined;
  Messages: undefined;
  Thread: { conversationId: string };
};

export type TabParamList = {
  Bill: undefined;
  Plan: undefined;
  Post: undefined;
  List: undefined;
  You: undefined;
};

export type RootNavigation = NavigationProp<RootStackParamList>;
